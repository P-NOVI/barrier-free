import importlib.util
import json
from datetime import date
from pathlib import Path

import pyarrow.parquet as pq
import pytest

STEPS = Path(__file__).resolve().parents[1] / "steps"
SERVICE = "CardSubwayTime"


def load_step(filename: str):
    spec = importlib.util.spec_from_file_location(filename[3:-3], STEPS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


subway = load_step("14_build_subway_ridership.py")


def api_row(month: str, line: str, station: str, on: float, off: float) -> dict:
    """API 한 행. 시간 h 의 승차는 on + h, 하차는 off + h 로 채운다."""
    row = {
        "USE_MM": month,
        "SBWY_ROUT_LN_NM": line,
        "STTN": station,
        "JOB_YMD": "20261103",
    }
    for hour in range(24):
        row[f"HR_{hour}_GET_ON_NOPE"] = on + hour
        row[f"HR_{hour}_GET_OFF_NOPE"] = off + hour
    return row


def ok_body(rows: list[dict], total: int | None = None) -> str:
    return json.dumps(
        {
            SERVICE: {
                "list_total_count": len(rows) if total is None else total,
                "RESULT": {"CODE": "INFO-000", "MESSAGE": "정상 처리되었습니다"},
                "row": rows,
            }
        },
        ensure_ascii=False,
    )


def test_month_range_crosses_year() -> None:
    assert subway.month_range("2023-12", "2024-02") == [
        "2023-12",
        "2024-01",
        "2024-02",
    ]


def test_period_defaults_to_previous_month() -> None:
    config = {"start_month": "2026-09", "end_month": None}
    assert subway.period(config, date(2026, 11, 5)) == ["2026-09", "2026-10"]
    january = {"start_month": "2026-11", "end_month": None}
    assert subway.period(january, date(2027, 1, 3)) == ["2026-11", "2026-12"]


def test_period_uses_end_month_and_rejects_empty_range() -> None:
    config = {"start_month": "2024-01", "end_month": "2024-03"}
    assert subway.period(config, date(2026, 11, 5))[-1] == "2024-03"
    with pytest.raises(SystemExit):
        subway.period({"start_month": "2026-11", "end_month": None}, date(2026, 11, 5))


def test_parse_response_ok() -> None:
    rows = [api_row("202610", "1호선", "서울역", 10.0, 20.0)]
    assert subway.parse_response(ok_body(rows), SERVICE, 1000) == rows


def test_parse_response_no_data_is_none() -> None:
    body = json.dumps(
        {"RESULT": {"CODE": "INFO-200", "MESSAGE": "해당하는 데이터가 없습니다."}}
    )
    assert subway.parse_response(body, SERVICE, 1000) is None


def test_parse_response_stops_on_xml_key_error() -> None:
    body = (
        "<RESULT><CODE>INFO-100</CODE>"
        "<MESSAGE>인증키가 유효하지 않습니다.</MESSAGE></RESULT>"
    )
    with pytest.raises(SystemExit, match="INFO-100"):
        subway.parse_response(body, SERVICE, 1000)


def test_parse_response_stops_when_month_exceeds_page_size() -> None:
    rows = [api_row("202610", "1호선", "서울역", 1.0, 1.0)]
    with pytest.raises(SystemExit):
        subway.parse_response(ok_body(rows, total=1001), SERVICE, 1000)


def test_to_rows_spreads_hours_and_sorts_by_month() -> None:
    loaded = {
        "2026-10": [api_row("202610", "2호선", "시청", 10.0, 20.0)],
        "2026-09": [api_row("202609", "1호선", "서울역", 699.0, 76.0)],
    }
    rows = subway.to_rows(loaded)
    assert len(rows) == 48
    assert rows[0] == {
        "month": "2026-09",
        "line": "1호선",
        "station": "서울역",
        "hour": 0,
        "boardings": 699,
        "alightings": 76,
    }
    assert rows[23]["hour"] == 23
    assert rows[23]["boardings"] == 722
    assert rows[24]["month"] == "2026-10"
    assert rows[24]["alightings"] == 20


def test_load_months_fetches_missing_months_and_skips_no_data(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(subway, "data_path", lambda relative: tmp_path / relative)
    config = {"raw_dir": "raw"}
    saved = [api_row("202608", "1호선", "서울역", 1.0, 2.0)]
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "2026-08.json").write_text(
        json.dumps(saved, ensure_ascii=False), encoding="utf-8"
    )
    fresh = [api_row("202609", "1호선", "시청", 3.0, 4.0)]
    asked: list[str] = []

    def fetch_month(month: str) -> list[dict] | None:
        asked.append(month)
        return fresh if month == "2026-09" else None

    months = ["2026-08", "2026-09", "2026-10"]
    loaded, missing, fetched = subway.load_months(config, months, fetch_month)

    assert asked == ["2026-09", "2026-10"]
    assert loaded == {"2026-08": saved, "2026-09": fresh}
    assert missing == ["2026-10"]
    assert fetched == 1
    assert (tmp_path / "raw" / "2026-09.json").exists()
    # 자료가 없는 달은 저장하지 않아 다음 실행에서 다시 받는다.
    assert not (tmp_path / "raw" / "2026-10.json").exists()


def test_write_parquet_and_report(tmp_path: Path) -> None:
    rows = subway.to_rows(
        {
            "2026-10": [
                api_row("202610", "1호선", "서울역", 5.0, 6.0),
                api_row("202610", "4호선", "서울역", 7.0, 8.0),
            ]
        }
    )
    output = tmp_path / "hourly.parquet"
    subway.write_parquet(rows, output)
    table = pq.read_table(output)
    assert table.column_names == [
        "month",
        "line",
        "station",
        "hour",
        "boardings",
        "alightings",
    ]
    assert table.num_rows == 48

    report = subway.make_report(rows, ["2026-10", "2026-11"], ["2026-11"], 1)
    assert report["months"] == 2
    assert report["months_with_data"] == 1
    assert report["missing_months"] == ["2026-11"]
    assert report["stations"] == 2
    assert report["lines"] == ["1호선", "4호선"]
