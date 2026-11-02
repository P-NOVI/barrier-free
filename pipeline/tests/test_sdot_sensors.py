import importlib.util
from pathlib import Path

import pytest

STEPS = Path(__file__).resolve().parents[1] / "steps"
BOUNDS = {"min_lat": 37.4, "max_lat": 37.75, "min_lon": 126.7, "max_lon": 127.2}
HEADER = ("순번", "방문자 센서코드", "시리얼번호", "주소", "위도", "경도")


def load_step(filename: str):
    spec = importlib.util.spec_from_file_location(filename[3:-3], STEPS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


export_sensors = load_step("05_export_sdot_sensors.py")


def test_parse_sensors_accepts_numbers_and_strings() -> None:
    rows = [
        HEADER,
        (1, 2992, "V02Q1", "서울특별시 양천구 신월동 805", 37.532462634, 126.833076323),
        (
            2,
            2993,
            "V02Q2",
            " 서울특별시 도봉구 창동 585-13 ",
            "37.63994636",
            "127.0360107",
        ),
        (None, None, None, None, None, None),
    ]
    assert export_sensors.parse_sensors(rows, BOUNDS) == [
        {
            "code": 2992,
            "lon": 126.833076,
            "lat": 37.532463,
            "address": "서울특별시 양천구 신월동 805",
        },
        {
            "code": 2993,
            "lon": 127.036011,
            "lat": 37.639946,
            "address": "서울특별시 도봉구 창동 585-13",
        },
    ]


def test_parse_sensors_rejects_outside_seoul() -> None:
    rows = [HEADER, (1, 2992, "V02Q1", "주소", 35.0, 126.8)]
    with pytest.raises(SystemExit, match="2992"):
        export_sensors.parse_sensors(rows, BOUNDS)


def test_parse_sensors_rejects_duplicate_code() -> None:
    rows = [
        HEADER,
        (1, 2992, "V02Q1", "주소1", 37.5, 126.9),
        (2, 2992, "V02Q2", "주소2", 37.6, 127.0),
    ]
    with pytest.raises(SystemExit, match="중복"):
        export_sensors.parse_sensors(rows, BOUNDS)
