"""공휴일을 받아 날짜별 달력 calendar/daily.parquet 으로 정리한다.

실행: pipeline/ 에서 uv run python steps/12_build_calendar.py
- 출처: 공공데이터포털 한국천문연구원 특일 정보 getRestDeInfo (대체·임시공휴일 포함).
- 키는 pipeline/.env 의 DATA_GO_KR_API_KEY 다. 디코딩(Decoding) 키를 넣는다.
- 월마다 raw/calendar/holidays/YYYY-MM.json 으로 저장하고, 있는 달은 건너뛴다.
  다시 받으려면 그 파일을 지운다(임시공휴일이 새로 생긴 달 등).
- 출력: interim/calendar/daily.parquet 과 daily_report.json
  열: date, is_holiday, holiday_name, is_off_day, off_run_length, in_long_holiday,
      days_to_long_holiday, days_since_long_holiday
  - is_off_day: 공휴일 또는 토·일요일
  - off_run_length: 그날이 속한 연속 휴일 묶음의 길이(쉬는 날이 아니면 0)
  - in_long_holiday: 묶음 길이가 long_holiday_min_days 이상인 연휴 안에 있는지
  - days_to_long_holiday / days_since_long_holiday: 다음 연휴 첫날까지, 지난 연휴 마지막
    날부터 며칠인지(연휴 안은 0). 받은 기간 안에 연휴가 없으면 빈 값이다.
그래프(00~04 단계)와 관계가 없어서 run_all.py 에 넣지 않고 따로 실행한다.
"""

import argparse
import json
import os
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from common import CONFIG_PATH, data_path, load_config

OK_CODE = "00"
HOLIDAY_FLAG = "Y"
SATURDAY = 5  # date.weekday() 기준
PARQUET_COMPRESSION = "zstd"
KEY_ENV = "DATA_GO_KR_API_KEY"

Item = dict[str, Any]
# (연, 월) → 공휴일 항목 목록
FetchMonth = Callable[[int, int], list[Item]]


def month_range(start: str, end: str) -> list[tuple[int, int]]:
    """'2023-12' ~ '2024-02' → [(2023, 12), (2024, 1), (2024, 2)]"""
    (y, m), (end_y, end_m) = (tuple(map(int, s.split("-"))) for s in (start, end))
    months = []
    while (y, m) <= (end_y, end_m):
        months.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return months


def parse_items(body: dict[str, Any]) -> list[Item]:
    """응답 본문의 항목 목록. 항목이 없으면 items 가 빈 문자열, 하나면 dict 로 온다."""
    items = body["items"]
    if not items:
        return []
    item = items["item"]
    return [item] if isinstance(item, dict) else item


def parse_locdate(value: int | str) -> date:
    text = str(value)
    return date(int(text[:4]), int(text[4:6]), int(text[6:]))


def month_fetcher(config: dict[str, Any], key: str) -> FetchMonth:
    def fetch_month(year: int, month: int) -> list[Item]:
        label = f"{year}-{month:02d}"
        query = urllib.parse.urlencode(
            {
                "serviceKey": key,
                "solYear": year,
                "solMonth": f"{month:02d}",
                "numOfRows": config["page_size"],
                "_type": "json",
            }
        )
        url = f"{config['url']}/{config['operation']}?{query}"
        for attempt in range(1, config["attempts"] + 1):
            try:
                with urllib.request.urlopen(url, timeout=config["timeout_s"]) as r:
                    response = json.load(r)["response"]
                code = response["header"]["resultCode"]
                if code != OK_CODE:
                    raise SystemExit(f"{label} 응답 코드 {code}: 키를 확인하세요.")
                body = response["body"]
                if int(body["totalCount"]) > config["page_size"]:
                    raise SystemExit(f"{label} 항목이 page_size 를 넘습니다.")
                return parse_items(body)
            except (OSError, KeyError, ValueError, TypeError) as error:
                # 키가 담긴 URL 이 보이지 않게 오류 종류만 남긴다.
                if attempt == config["attempts"]:
                    raise SystemExit(
                        f"{label} 받기 실패: {type(error).__name__}"
                    ) from None
                time.sleep(config["retry_wait_s"])
        raise AssertionError("unreachable")

    return fetch_month


def month_path(config: dict[str, Any], year: int, month: int) -> Path:
    return data_path(config["raw_dir"]) / f"{year}-{month:02d}.json"


def load_holidays(
    config: dict[str, Any], fetch_month: FetchMonth
) -> tuple[dict[date, str], int]:
    """기간의 공휴일(날짜 → 이름)과 새로 받은 달 수. 있는 달은 파일을 읽는다."""
    holidays: dict[date, str] = {}
    fetched = 0
    for year, month in month_range(config["start_month"], config["end_month"]):
        path = month_path(config, year, month)
        if path.exists():
            items = json.loads(path.read_text(encoding="utf-8"))
        else:
            items = fetch_month(year, month)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
            fetched += 1
            print(f"{year}-{month:02d}: {len(items)}건", flush=True)
        for item in items:
            if item["isHoliday"] == HOLIDAY_FLAG:
                holidays[parse_locdate(item["locdate"])] = item["dateName"]
    return holidays, fetched


def run_lengths(off: list[bool]) -> list[int]:
    """쉬는 날이 이어진 묶음의 길이를 묶음 안 모든 날에 적는다. 평일은 0."""
    lengths = [0] * len(off)
    i = 0
    while i < len(off):
        if not off[i]:
            i += 1
            continue
        j = i
        while j < len(off) and off[j]:
            j += 1
        lengths[i:j] = [j - i] * (j - i)
        i = j
    return lengths


def build_daily(
    holidays: dict[date, str], first: date, last: date, long_min_days: int
) -> list[dict[str, Any]]:
    """first ~ last 의 날짜별 행. 연휴는 연속된 쉬는 날(공휴일·주말) 묶음으로 센다."""
    days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    off = [d in holidays or d.weekday() >= SATURDAY for d in days]
    lengths = run_lengths(off)
    in_long = [length >= long_min_days for length in lengths]

    since: list[int | None] = []
    last_long: int | None = None
    for i, flag in enumerate(in_long):
        if flag:
            last_long = i
        since.append(None if last_long is None else i - last_long)
    to: list[int | None] = [None] * len(days)
    next_long: int | None = None
    for i in reversed(range(len(days))):
        if in_long[i]:
            next_long = i
        to[i] = None if next_long is None else next_long - i

    return [
        {
            "date": d,
            "is_holiday": d in holidays,
            "holiday_name": holidays.get(d),
            "is_off_day": off[i],
            "off_run_length": lengths[i],
            "in_long_holiday": in_long[i],
            "days_to_long_holiday": to[i],
            "days_since_long_holiday": since[i],
        }
        for i, d in enumerate(days)
    ]


def write_parquet(rows: list[dict[str, Any]], path: Path) -> None:
    schema = pa.schema(
        [
            ("date", pa.date32()),
            ("is_holiday", pa.bool_()),
            ("holiday_name", pa.string()),
            ("is_off_day", pa.bool_()),
            ("off_run_length", pa.int8()),
            ("in_long_holiday", pa.bool_()),
            ("days_to_long_holiday", pa.int16()),
            ("days_since_long_holiday", pa.int16()),
        ]
    )
    columns = {name: [row[name] for row in rows] for name in schema.names}
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.table(columns, schema=schema), path, compression=PARQUET_COMPRESSION
    )


def make_report(rows: list[dict[str, Any]], fetched: int) -> dict[str, Any]:
    holidays = [r for r in rows if r["is_holiday"]]
    return {
        "first_date": rows[0]["date"].isoformat(),
        "last_date": rows[-1]["date"].isoformat(),
        "days": len(rows),
        "months_fetched_now": fetched,
        "holidays": len(holidays),
        "holidays_on_weekend": sum(r["date"].weekday() >= SATURDAY for r in holidays),
        "off_days": sum(r["is_off_day"] for r in rows),
        "long_holiday_days": sum(r["in_long_holiday"] for r in rows),
        "holiday_names": sorted({r["holiday_name"] for r in holidays}),
    }


def last_day_of_month(year: int, month: int) -> date:
    return date(year + month // 12, month % 12 + 1, 1) - timedelta(days=1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    config = load_config(parser.parse_args().config)["calendar"]
    key = os.environ.get(KEY_ENV, "").strip()

    months = month_range(config["start_month"], config["end_month"])
    if not key and any(not month_path(config, *m).exists() for m in months):
        raise SystemExit(f"pipeline/.env 에 {KEY_ENV} 가 없습니다.")
    started = time.time()
    holidays, fetched = load_holidays(config, month_fetcher(config, key))

    rows = build_daily(
        holidays,
        date(*months[0], 1),
        last_day_of_month(*months[-1]),
        config["long_holiday_min_days"],
    )
    output = data_path(config["output"])
    write_parquet(rows, output)
    report = make_report(rows, fetched)
    report_path = data_path(config["report"])
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"{report['days']}일, 공휴일 {report['holidays']}일, "
        f"연휴 {report['long_holiday_days']}일 → {output} "
        f"({time.time() - started:.0f}s)"
    )


if __name__ == "__main__":
    main()
