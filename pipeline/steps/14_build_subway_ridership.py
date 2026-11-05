"""지하철 호선별 역별 승하차 인원을 받아 날짜별 표 subway/daily.parquet 으로 정리한다.

실행: pipeline/ 에서 uv run python steps/14_build_subway_ridership.py
- 출처: 서울 열린데이터광장 서울시 지하철호선별 역별 승하차 인원 정보
  (CardSubwayStatsNew).
- 키는 pipeline/.env 의 SEOUL_API_KEY(서울 열린데이터광장 인증키, S-DoT 와 같은 키)다.
- 날마다 raw/subway/ridership/YYYYMMDD.json 으로 저장하고, 있는 날은 건너뛴다.
  자료가 없는 날(아직 등록 전이거나 API 보관 기간 밖)은 저장하지 않고 보고서에 남긴다.
- 출력: interim/subway/daily.parquet 과 daily_report.json
  열: date, line, station, boardings(승차), alightings(하차)
그래프(00~04 단계)와 관계가 없어서 run_all.py 에 넣지 않고 따로 실행한다.
"""

import argparse
import json
import os
import re
import time
import urllib.request
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from common import CONFIG_PATH, data_path, load_config

OK_CODE = "INFO-000"
NO_DATA_CODE = "INFO-200"
DATE_FORMAT = "%Y%m%d"
PARQUET_COMPRESSION = "zstd"
KEY_ENV = "SEOUL_API_KEY"
# 키 오류 같은 응답은 json 경로로 불러도 XML 로 온다.
XML_CODE = re.compile(r"<CODE>\s*([^<]+?)\s*</CODE>")

Row = dict[str, Any]
# 날짜 → 그날 행 목록. 자료가 없으면 None
FetchDay = Callable[[date], list[Row] | None]


def date_range(first: date, last: date) -> list[date]:
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def period(config: dict[str, Any], today: date) -> tuple[date, date]:
    """받을 기간. end_date 가 비어 있으면 오늘에서 등록 지연 lag_days 를 뺀 날까지."""
    first = parse_date(config["start_date"])
    end = config.get("end_date")
    last = parse_date(end) if end else today - timedelta(days=config["lag_days"])
    if last < first:
        raise SystemExit(f"기간이 비었습니다: {first} ~ {last}")
    return first, last


def parse_response(text: str, service: str, page_size: int) -> list[Row] | None:
    """응답 본문 → 행 목록. 그날 자료가 없으면 None, 그 밖의 오류 코드는 멈춘다."""
    if text.lstrip().startswith("<"):
        match = XML_CODE.search(text)
        code = match.group(1) if match else "XML"
        raise SystemExit(f"응답 코드 {code}: {KEY_ENV} 를 확인하세요.")
    data = json.loads(text)
    body = data.get(service, data)
    result = body["RESULT"]
    if result["CODE"] == NO_DATA_CODE:
        return None
    if result["CODE"] != OK_CODE:
        raise SystemExit(f"응답 코드 {result['CODE']}: {result['MESSAGE']}")
    if body["list_total_count"] > page_size:
        raise SystemExit("하루 행 수가 page_size 를 넘습니다. page_size 를 늘리세요.")
    return body["row"]


def day_fetcher(config: dict[str, Any], key: str) -> FetchDay:
    def fetch_day(day: date) -> list[Row] | None:
        label = day.strftime(DATE_FORMAT)
        url = (
            f"{config['url']}/{key}/json/{config['service']}/"
            f"1/{config['page_size']}/{label}"
        )
        for attempt in range(1, config["attempts"] + 1):
            try:
                with urllib.request.urlopen(url, timeout=config["timeout_s"]) as r:
                    text = r.read().decode("utf-8")
                return parse_response(text, config["service"], config["page_size"])
            except (OSError, KeyError, ValueError) as error:
                # 키가 담긴 URL 이 보이지 않게 오류 종류만 남긴다.
                if attempt == config["attempts"]:
                    raise SystemExit(
                        f"{label} 받기 실패: {type(error).__name__}"
                    ) from None
                time.sleep(config["retry_wait_s"])
        raise AssertionError("unreachable")

    return fetch_day


def day_path(config: dict[str, Any], day: date) -> Path:
    return data_path(config["raw_dir"]) / f"{day.strftime(DATE_FORMAT)}.json"


def load_days(
    config: dict[str, Any], days: list[date], fetch_day: FetchDay
) -> tuple[dict[date, list[Row]], list[date], int]:
    """날짜별 원본 행, 자료가 없는 날, 새로 받은 날 수. 있는 날은 파일을 읽는다."""
    loaded: dict[date, list[Row]] = {}
    missing: list[date] = []
    fetched = 0
    for day in days:
        path = day_path(config, day)
        if path.exists():
            loaded[day] = json.loads(path.read_text(encoding="utf-8"))
            continue
        rows = fetch_day(day)
        if rows is None:
            missing.append(day)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        loaded[day] = rows
        fetched += 1
        print(f"{day}: {len(rows)}행", flush=True)
    return loaded, missing, fetched


def count(value: str | int | float) -> int:
    """인원 값. 문자열("65975")이나 실수("699.0")로 온다."""
    return int(float(value))


def to_rows(loaded: dict[date, list[Row]]) -> list[Row]:
    return [
        {
            "date": day,
            "line": row["SBWY_ROUT_LN_NM"],
            "station": row["SBWY_STNS_NM"],
            "boardings": count(row["GTON_TNOPE"]),
            "alightings": count(row["GTOFF_TNOPE"]),
        }
        for day in sorted(loaded)
        for row in loaded[day]
    ]


def write_parquet(rows: list[Row], path: Path) -> None:
    schema = pa.schema(
        [
            ("date", pa.date32()),
            ("line", pa.string()),
            ("station", pa.string()),
            ("boardings", pa.int32()),
            ("alightings", pa.int32()),
        ]
    )
    columns = {name: [row[name] for row in rows] for name in schema.names}
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.table(columns, schema=schema), path, compression=PARQUET_COMPRESSION
    )


def make_report(
    rows: list[Row], first: date, last: date, missing: list[date], fetched: int
) -> dict[str, Any]:
    return {
        "first_date": first.isoformat(),
        "last_date": last.isoformat(),
        "days": (last - first).days + 1,
        "days_with_data": len({row["date"] for row in rows}),
        "days_fetched_now": fetched,
        "missing_days": [day.isoformat() for day in missing],
        "rows": len(rows),
        "stations": len({(row["line"], row["station"]) for row in rows}),
        "lines": sorted({row["line"] for row in rows}),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    config = load_config(parser.parse_args().config)["subway_ridership"]
    key = os.environ.get(KEY_ENV, "").strip()

    first, last = period(config, date.today())
    days = date_range(first, last)
    if not key and any(not day_path(config, day).exists() for day in days):
        raise SystemExit(f"pipeline/.env 에 {KEY_ENV} 가 없습니다.")
    started = time.time()
    loaded, missing, fetched = load_days(config, days, day_fetcher(config, key))
    rows = to_rows(loaded)
    if not rows:
        raise SystemExit(
            f"{first} ~ {last} 에 받은 자료가 없습니다. 기간을 확인하세요."
        )

    output = data_path(config["output"])
    write_parquet(rows, output)
    report = make_report(rows, first, last, missing, fetched)
    report_path = data_path(config["report"])
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"{report['days_with_data']}/{report['days']}일, {report['rows']}행, "
        f"역 {report['stations']}곳 → {output} ({time.time() - started:.0f}s)"
    )


if __name__ == "__main__":
    main()
