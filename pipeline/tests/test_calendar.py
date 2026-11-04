import importlib.util
import json
from datetime import date
from pathlib import Path

import pytest

STEPS = Path(__file__).resolve().parents[1] / "steps"


def load_step(filename: str):
    spec = importlib.util.spec_from_file_location(filename[3:-3], STEPS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


calendar = load_step("12_build_calendar.py")


def item(locdate: int, name: str = "공휴일", flag: str = "Y") -> dict:
    return {"dateName": name, "isHoliday": flag, "locdate": locdate, "seq": 1}


def test_month_range_crosses_year() -> None:
    assert calendar.month_range("2023-11", "2024-02") == [
        (2023, 11),
        (2023, 12),
        (2024, 1),
        (2024, 2),
    ]


def test_parse_items_handles_empty_single_and_many() -> None:
    assert calendar.parse_items({"items": ""}) == []
    assert calendar.parse_items({"items": {"item": item(20260101)}}) == [item(20260101)]
    many = [item(20260101), item(20260102)]
    assert calendar.parse_items({"items": {"item": many}}) == many


def test_parse_locdate() -> None:
    assert calendar.parse_locdate(20251003) == date(2025, 10, 3)


def test_run_lengths() -> None:
    off = [False, True, True, False, True, True, True, True, False]
    assert calendar.run_lengths(off) == [0, 2, 2, 0, 4, 4, 4, 4, 0]


def test_build_daily_long_holiday_and_distances() -> None:
    # 2026-02-14(토) ~ 02-18(수)는 토·일·설날 연휴 3일 = 5일 묶음
    holidays = {
        date(2026, 2, 16): "설날",
        date(2026, 2, 17): "설날",
        date(2026, 2, 18): "설날",
    }
    rows = {
        r["date"]: r
        for r in calendar.build_daily(holidays, date(2026, 2, 9), date(2026, 2, 28), 3)
    }
    assert rows[date(2026, 2, 16)]["is_holiday"] is True
    assert rows[date(2026, 2, 16)]["holiday_name"] == "설날"
    assert rows[date(2026, 2, 15)]["off_run_length"] == 5
    assert rows[date(2026, 2, 15)]["in_long_holiday"] is True
    assert rows[date(2026, 2, 13)]["days_to_long_holiday"] == 1
    assert rows[date(2026, 2, 13)]["days_since_long_holiday"] is None
    assert rows[date(2026, 2, 19)]["days_since_long_holiday"] == 1
    assert rows[date(2026, 2, 19)]["days_to_long_holiday"] is None
    # 연휴가 아닌 주말(2일)은 쉬는 날이지만 연휴가 아니다.
    assert rows[date(2026, 2, 21)]["is_off_day"] is True
    assert rows[date(2026, 2, 21)]["in_long_holiday"] is False
    assert rows[date(2026, 2, 21)]["days_since_long_holiday"] == 3


def test_load_holidays_fetches_missing_months_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(calendar, "data_path", lambda relative: tmp_path / relative)
    config = {"raw_dir": "raw", "start_month": "2026-01", "end_month": "2026-03"}
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "2026-01.json").write_text(
        json.dumps([item(20260101, "신정")]), encoding="utf-8"
    )
    calls: list[tuple[int, int]] = []

    def fetch(year: int, month: int) -> list[dict]:
        calls.append((year, month))
        return [item(20260301, "삼일절"), item(20260302, "기념일", flag="N")]

    holidays, fetched = calendar.load_holidays(config, fetch)

    assert calls == [(2026, 2), (2026, 3)]
    assert fetched == 2
    # isHoliday 가 N 인 날은 쉬는 날이 아니다.
    assert holidays == {date(2026, 1, 1): "신정", date(2026, 3, 1): "삼일절"}
    assert (tmp_path / "raw" / "2026-02.json").exists()


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None

    def read(self, *args) -> bytes:
        return json.dumps(self.payload).encode()


CONFIG = {
    "url": "http://example.test",
    "operation": "op",
    "page_size": 100,
    "timeout_s": 1,
    "attempts": 2,
    "retry_wait_s": 0,
}


def response(code: str, total: int = 0, items: object = "") -> dict:
    return {
        "response": {
            "header": {"resultCode": code},
            "body": {"items": items, "totalCount": total},
        }
    }


def test_fetch_month_parses_response(monkeypatch) -> None:
    payload = response("00", 1, {"item": item(20260101)})
    monkeypatch.setattr(
        calendar.urllib.request, "urlopen", lambda *a, **k: FakeResponse(payload)
    )
    assert calendar.month_fetcher(CONFIG, "key")(2026, 1) == [item(20260101)]


def test_fetch_month_stops_on_error_code(monkeypatch) -> None:
    monkeypatch.setattr(
        calendar.urllib.request,
        "urlopen",
        lambda *a, **k: FakeResponse(response("30")),
    )
    with pytest.raises(SystemExit, match="30"):
        calendar.month_fetcher(CONFIG, "key")(2026, 1)


def test_fetch_month_error_hides_key(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise OSError("http://example.test?serviceKey=SECRET")

    monkeypatch.setattr(calendar.urllib.request, "urlopen", fail)
    with pytest.raises(SystemExit) as error:
        calendar.month_fetcher(CONFIG, "SECRET")(2026, 1)
    assert "SECRET" not in str(error.value)
