import importlib.util
import json
from datetime import date
from pathlib import Path

import pyarrow.parquet as pq
import pytest

STEPS = Path(__file__).resolve().parents[1] / "steps"
SERVICE = "CardSubwayStatsNew"


def load_step(filename: str):
    spec = importlib.util.spec_from_file_location(filename[3:-3], STEPS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


subway = load_step("14_build_subway_ridership.py")


def api_row(day: str, line: str, station: str, on: str, off: str) -> dict:
    return {
        "USE_YMD": day,
        "SBWY_ROUT_LN_NM": line,
        "SBWY_STNS_NM": station,
        "GTON_TNOPE": on,
        "GTOFF_TNOPE": off,
        "REG_YMD": "20261104",
    }


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


def test_period_defaults_to_today_minus_lag() -> None:
    config = {"start_date": "2026-11-01", "end_date": None, "lag_days": 3}
    assert subway.period(config, date(2026, 11, 5)) == (
        date(2026, 11, 1),
        date(2026, 11, 2),
    )


def test_period_uses_end_date_and_rejects_empty_range() -> None:
    config = {"start_date": "2026-03-01", "end_date": "2026-03-03", "lag_days": 3}
    assert subway.period(config, date(2026, 11, 5))[1] == date(2026, 3, 3)
    with pytest.raises(SystemExit):
        subway.period(
            {"start_date": "2026-11-04", "end_date": None, "lag_days": 3},
            date(2026, 11, 5),
        )


def test_parse_response_ok() -> None:
    rows = [api_row("20261101", "1호선", "서울역", "65975", "64420")]
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


def test_parse_response_stops_when_day_exceeds_page_size() -> None:
    rows = [api_row("20261101", "1호선", "서울역", "1", "1")]
    with pytest.raises(SystemExit):
        subway.parse_response(ok_body(rows, total=1001), SERVICE, 1000)


def test_to_rows_converts_counts_and_sorts_by_date() -> None:
    loaded = {
        date(2026, 11, 2): [api_row("20261102", "2호선", "시청", "10", "20")],
        date(2026, 11, 1): [api_row("20261101", "1호선", "서울역", "699.0", "76")],
    }
    assert subway.to_rows(loaded) == [
        {
            "date": date(2026, 11, 1),
            "line": "1호선",
            "station": "서울역",
            "boardings": 699,
            "alightings": 76,
        },
        {
            "date": date(2026, 11, 2),
            "line": "2호선",
            "station": "시청",
            "boardings": 10,
            "alightings": 20,
        },
    ]


def test_load_days_fetches_missing_days_and_skips_no_data(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(subway, "data_path", lambda relative: tmp_path / relative)
    config = {"raw_dir": "raw"}
    saved = [api_row("20261101", "1호선", "서울역", "1", "2")]
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "20261101.json").write_text(
        json.dumps(saved, ensure_ascii=False), encoding="utf-8"
    )
    fresh = [api_row("20261102", "1호선", "시청", "3", "4")]
    asked: list[date] = []

    def fetch_day(day: date) -> list[dict] | None:
        asked.append(day)
        return fresh if day == date(2026, 11, 2) else None

    days = [date(2026, 11, 1), date(2026, 11, 2), date(2026, 11, 3)]
    loaded, missing, fetched = subway.load_days(config, days, fetch_day)

    assert asked == [date(2026, 11, 2), date(2026, 11, 3)]
    assert loaded == {date(2026, 11, 1): saved, date(2026, 11, 2): fresh}
    assert missing == [date(2026, 11, 3)]
    assert fetched == 1
    assert (tmp_path / "raw" / "20261102.json").exists()
    # 자료가 없는 날은 저장하지 않아 다음 실행에서 다시 받는다.
    assert not (tmp_path / "raw" / "20261103.json").exists()


def test_write_parquet_and_report(tmp_path: Path) -> None:
    rows = subway.to_rows(
        {
            date(2026, 11, 1): [
                api_row("20261101", "1호선", "서울역", "5", "6"),
                api_row("20261101", "4호선", "서울역", "7", "8"),
            ]
        }
    )
    output = tmp_path / "daily.parquet"
    subway.write_parquet(rows, output)
    table = pq.read_table(output)
    assert table.column_names == ["date", "line", "station", "boardings", "alightings"]
    assert table.num_rows == 2

    report = subway.make_report(
        rows, date(2026, 11, 1), date(2026, 11, 2), [date(2026, 11, 2)], 1
    )
    assert report["days"] == 2
    assert report["days_with_data"] == 1
    assert report["missing_days"] == ["2026-11-02"]
    assert report["stations"] == 2
    assert report["lines"] == ["1호선", "4호선"]
