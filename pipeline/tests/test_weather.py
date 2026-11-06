import importlib.util
from datetime import datetime
from pathlib import Path

import numpy as np

STEPS = Path(__file__).resolve().parents[1] / "steps"
OBS_HEADER = "지점,지점명,일시,기온(°C),강수량(mm)"
STATION_HEADER = "지점,시작일,종료일,지점명,지점주소,위도,경도"


def load_step(filename: str):
    spec = importlib.util.spec_from_file_location(filename[3:-3], STEPS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


weather = load_step("11_build_weather.py")


def write_csv(
    path: Path, header: str, rows: list[str], encoding: str = "cp949"
) -> Path:
    path.write_text("\n".join([header, *rows]) + "\n", encoding=encoding)
    return path


def hour(h: int) -> datetime:
    return datetime(2024, 1, 1, h)


def observations(rows: dict[tuple[int, int], tuple[float | None, float | None]]):
    return weather.Observations(
        values={(code, hour(h)): value for (code, h), value in rows.items()},
        bad_rows={},
        rows={},
    )


def test_stations_use_current_row_and_find_district(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path / "stations.csv",
        "\n" + STATION_HEADER,
        [
            "400,2025-09-12,,강남,서울특별시 강남구 일원동,37.4982,127.0816",
            "400,2019-05-29,2025-09-12,강남,서울특별시 강남구 삼성동,37.5134,127.0467",
            "419,2020-01-01,,중구,서울특별시 중구 예장동,37.5524,126.9874",
            "999,2020-01-01,,섬,제주특별자치도 제주시 한림읍,33.4,126.2",
        ],
    )

    stations = weather.read_stations(path)

    assert stations[400].lat == 37.4982
    assert stations[400].district == "강남구"
    assert stations[419].district == "중구"
    assert stations[999].district is None


def test_observations_keep_blank_values_empty_and_drop_duplicates(
    tmp_path: Path,
) -> None:
    first = write_csv(
        tmp_path / "a.csv",
        OBS_HEADER,
        ["400,강남,2024-01-01 00:00,-.5,", "400,강남,2024-01-01 01:00,.2,0"],
        "cp949",
    )
    second = write_csv(
        tmp_path / "b.csv",
        OBS_HEADER,
        [
            "400,강남,2024-01-01 01:00,.2,0",
            "400,강남,2024-01-01 00:00,-.4,1.5",
            "400,강남,2024-01-01 02:30,1.0,0",
            "abc,강남,2024-01-01 03:00,1.0,0",
        ],
        "utf-8-sig",
    )

    result = weather.read_observations([first, second])

    assert result.values[(400, hour(1))] == (0.2, 0.0)
    # 뒤에 읽은 값을 쓴다.
    assert result.values[(400, hour(0))] == (-0.4, 1.5)
    assert result.duplicates_removed == 2
    assert result.conflicting_duplicates == 1
    assert result.bad_rows == {"b.csv": 2}


def test_blank_rain_is_not_zero(tmp_path: Path) -> None:
    path = write_csv(tmp_path / "a.csv", OBS_HEADER, ["400,강남,2024-01-01 00:00,1,"])

    result = weather.read_observations([path])

    assert result.values[(400, hour(0))] == (1.0, None)


def test_assign_uses_own_district_stations_and_nearest_for_others() -> None:
    stations = {
        1: weather.Station(1, 37.50, 127.00, "강남구"),
        2: weather.Station(2, 37.52, 127.02, "강남구"),
        3: weather.Station(3, 37.60, 127.00, "성북구"),
        4: weather.Station(4, 37.45, 126.90, "금천구"),
    }
    centers = {
        "Gangnam-gu": (37.51, 127.01),
        "Jongno-gu": (37.58, 126.99),
        "Seoul_Grand_Park": (37.43, 127.02),
    }
    korean = {"Gangnam-gu": "강남구", "Jongno-gu": "종로구", "Seoul_Grand_Park": None}

    assigned, nearest_km = weather.assign_stations(
        list(centers), korean, stations, centers
    )

    assert assigned["Gangnam-gu"] == [1, 2]
    assert assigned["Jongno-gu"] == [3]
    assert assigned["Seoul_Grand_Park"] == [1]
    assert set(nearest_km) == {"Jongno-gu", "Seoul_Grand_Park"}
    assert nearest_km["Jongno-gu"] < 5


def test_hourly_averages_stations_and_fills_from_neighbors() -> None:
    obs = observations(
        {
            (1, 0): (10.0, 0.0),
            (2, 0): (20.0, 2.0),
            (1, 1): (11.0, 0.0),
            (2, 1): (None, None),
            (3, 0): (30.0, 0.0),
            (3, 1): (31.0, 4.0),
        }
    )
    assigned = {"A": [1, 2], "B": [3]}
    centers = {"A": (37.5, 127.0), "B": (37.6, 127.0)}

    table, stats = weather.build_hourly(obs, assigned, centers, 3, 3)
    rows = {(r["district"], r["hour"].hour): r for r in table.to_pylist()}

    assert rows[("A", 0)]["temp"] == 15.0
    assert rows[("A", 0)]["rain_mm"] == 1.0
    # 같은 구의 다른 지점에 값이 있으면 그 값만 쓴다.
    assert rows[("A", 1)]["temp"] == 11.0
    assert stats["missing_after_fill"] == {"temp": 0, "rain_mm": 0}


def test_hourly_fills_district_gap_from_nearest_district() -> None:
    obs = observations(
        {
            (1, 0): (10.0, 0.0),
            (1, 1): (None, None),
            (2, 0): (20.0, 1.0),
            (2, 1): (22.0, 3.0),
            (3, 0): (40.0, 0.0),
            (3, 1): (44.0, 9.0),
        }
    )
    assigned = {"A": [1], "B": [2], "C": [3]}
    centers = {"A": (37.50, 127.0), "B": (37.51, 127.0), "C": (37.90, 127.0)}

    table, stats = weather.build_hourly(obs, assigned, centers, 1, 3)
    rows = {(r["district"], r["hour"].hour): r for r in table.to_pylist()}

    # 이웃 1개만 쓰므로 가장 가까운 B 의 값이다.
    assert rows[("A", 1)]["temp"] == 22.0
    assert rows[("A", 1)]["rain_mm"] == 3.0
    assert stats["missing_before_fill"] == {"temp": 1, "rain_mm": 1}


def test_short_gaps_are_interpolated_only_when_bounded() -> None:
    row = np.array([1.0, np.nan, np.nan, 4.0, np.nan, np.nan, np.nan, np.nan, 9.0])

    filled = weather.fill_short_gaps(row, 3)

    assert filled[:4].tolist() == [1.0, 2.0, 3.0, 4.0]
    assert np.isnan(filled[4:8]).all()

    edges = weather.fill_short_gaps(np.array([np.nan, 1.0, np.nan]), 3)
    assert np.isnan(edges[0]) and np.isnan(edges[2])
