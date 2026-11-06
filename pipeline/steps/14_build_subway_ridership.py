"""지하철 역별 시간대별 승하차 인원을 받아 subway/hourly.parquet 으로 정리한다.

실행: pipeline/ 에서 uv run python steps/14_build_subway_ridership.py
- 출처: 서울 열린데이터광장 서울시 지하철 호선별 역별 시간대별 승하차 인원 정보
  (OA-12252, CardSubwayTime). 교통카드 기준. 1~9호선 말고도 경부선·분당선·신림선 등
  27개 노선이 있다(2026-02~04 확인).
- 키는 pipeline/.env 의 SEOUL_API_KEY(서울 열린데이터광장 인증키, S-DoT 와 같은 키)다.
- 달마다 raw/subway/ridership_hourly/YYYY-MM.json 으로 저장하고, 있는 달은 건너뛴다.
  자료가 없는 달(아직 올라오기 전)은 저장하지 않고 보고서에 남긴다.
- 한 달 행이 page_size 를 넘으면 나눠 받는다. 원본은 받은 그대로 두고, 모든 값이 같은
  행은 표를 만들 때 하나만 남긴다(2026-03 은 API 가 같은 행을 두 번 준다).
- 출력: interim/subway/hourly.parquet 과 hourly_report.json
  열: month(YYYY-MM), line, station, hour, boardings(승차), alightings(하차)
  - 값은 그 달 그 시간대의 한 달 합계다. 날짜·요일로는 나뉘지 않는다.
  - hour 는 시작 시각이다(8 → 08~09시).
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
PARQUET_COMPRESSION = "zstd"
KEY_ENV = "SEOUL_API_KEY"
# 응답 행의 HR_0_GET_ON_NOPE ~ HR_23_GET_OFF_NOPE
HOURS = range(24)
# 키 오류 같은 응답은 json 경로로 불러도 XML 로 온다.
XML_CODE = re.compile(r"<CODE>\s*([^<]+?)\s*</CODE>")

Row = dict[str, Any]
# (이 쪽 행 목록, 그달 전체 행 수)
Page = tuple[list[Row], int]
# (시작 행, 끝 행) → 그 범위. 자료가 없으면 None
GetPage = Callable[[int, int], Page | None]
# 'YYYY-MM' → 그달 행 목록. 자료가 없으면 None
FetchMonth = Callable[[str], list[Row] | None]


def month_range(start: str, end: str) -> list[str]:
    """'2023-12' ~ '2024-02' → ['2023-12', '2024-01', '2024-02']"""
    (y, m), (end_y, end_m) = (tuple(map(int, s.split("-"))) for s in (start, end))
    months = []
    while (y, m) <= (end_y, end_m):
        months.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return months


def previous_month(today: date) -> str:
    return (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")


def period(config: dict[str, Any], today: date) -> list[str]:
    """받을 달 목록. end_month 가 비어 있으면 지난달까지."""
    end = config.get("end_month") or previous_month(today)
    months = month_range(config["start_month"], end)
    if not months:
        raise SystemExit(f"기간이 비었습니다: {config['start_month']} ~ {end}")
    return months


def parse_response(text: str, service: str) -> Page | None:
    """응답 본문 → (행 목록, 전체 행 수). 자료가 없으면 None, 다른 오류는 멈춘다."""
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
    return body["row"], body["list_total_count"]


def fetch_pages(get_page: GetPage, page_size: int) -> list[Row] | None:
    """API 는 한 번에 정해진 행 수까지만 주므로 page_size 씩 나눠 끝까지 받는다."""
    rows: list[Row] = []
    total: int | None = None
    while total is None or len(rows) < total:
        start = len(rows) + 1
        page = get_page(start, start + page_size - 1)
        if page is None and total is None:
            return None
        if page is None or not page[0]:
            raise SystemExit(f"{total}행 중 {len(rows)}행까지만 받았습니다.")
        part, total = page
        rows += part
    return rows


def month_fetcher(config: dict[str, Any], key: str) -> FetchMonth:
    def get_page(month: str, start: int, end: int) -> Page | None:
        url = (
            f"{config['url']}/{key}/json/{config['service']}/"
            f"{start}/{end}/{month.replace('-', '')}"
        )
        for attempt in range(1, config["attempts"] + 1):
            try:
                with urllib.request.urlopen(url, timeout=config["timeout_s"]) as r:
                    text = r.read().decode("utf-8")
                return parse_response(text, config["service"])
            except (OSError, KeyError, ValueError) as error:
                # 키가 담긴 URL 이 보이지 않게 오류 종류만 남긴다.
                if attempt == config["attempts"]:
                    raise SystemExit(
                        f"{month} 받기 실패: {type(error).__name__}"
                    ) from None
                time.sleep(config["retry_wait_s"])
        raise AssertionError("unreachable")

    def fetch_month(month: str) -> list[Row] | None:
        return fetch_pages(
            lambda start, end: get_page(month, start, end), config["page_size"]
        )

    return fetch_month


def month_path(config: dict[str, Any], month: str) -> Path:
    return data_path(config["raw_dir"]) / f"{month}.json"


def load_months(
    config: dict[str, Any], months: list[str], fetch_month: FetchMonth
) -> tuple[dict[str, list[Row]], list[str], int]:
    """달별 원본 행, 자료가 없는 달, 새로 받은 달 수. 있는 달은 파일을 읽는다."""
    loaded: dict[str, list[Row]] = {}
    missing: list[str] = []
    fetched = 0
    for month in months:
        path = month_path(config, month)
        if path.exists():
            loaded[month] = json.loads(path.read_text(encoding="utf-8"))
            continue
        rows = fetch_month(month)
        if rows is None:
            missing.append(month)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        loaded[month] = rows
        fetched += 1
        print(f"{month}: {len(rows)}행", flush=True)
    return loaded, missing, fetched


def drop_duplicates(
    loaded: dict[str, list[Row]],
) -> tuple[dict[str, list[Row]], dict[str, int]]:
    """모든 값이 같은 행은 하나만 남긴다(2026-03 은 API 가 같은 행을 두 번 준다).

    같은 호선·역인데 값이 다르면 어느 쪽이 맞는지 알 수 없어 멈춘다.
    반환: 달별 행, 달별 버린 행 수(버린 행이 있는 달만)
    """
    unique: dict[str, list[Row]] = {}
    dropped: dict[str, int] = {}
    for month, rows in loaded.items():
        kept: dict[tuple[str, str], Row] = {}
        for row in rows:
            station = (row["SBWY_ROUT_LN_NM"], row["STTN"])
            if station not in kept:
                kept[station] = row
            elif kept[station] != row:
                raise SystemExit(
                    f"{month} {station[0]} {station[1]}: 값이 다른 행이 둘 있습니다."
                )
        unique[month] = list(kept.values())
        if len(rows) > len(kept):
            dropped[month] = len(rows) - len(kept)
    return unique, dropped


def count(value: str | int | float) -> int:
    """인원 값. 실수("699.0")나 문자열로 온다."""
    return int(float(value))


def to_rows(loaded: dict[str, list[Row]]) -> list[Row]:
    """역 하나가 한 행에 24시간을 담아 오므로 시간마다 한 행으로 편다."""
    return [
        {
            "month": month,
            "line": row["SBWY_ROUT_LN_NM"],
            "station": row["STTN"],
            "hour": hour,
            "boardings": count(row[f"HR_{hour}_GET_ON_NOPE"]),
            "alightings": count(row[f"HR_{hour}_GET_OFF_NOPE"]),
        }
        for month in sorted(loaded)
        for row in loaded[month]
        for hour in HOURS
    ]


def write_parquet(rows: list[Row], path: Path) -> None:
    schema = pa.schema(
        [
            ("month", pa.string()),
            ("line", pa.string()),
            ("station", pa.string()),
            ("hour", pa.int8()),
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
    rows: list[Row],
    months: list[str],
    missing: list[str],
    fetched: int,
    dropped: dict[str, int],
) -> dict[str, Any]:
    return {
        "first_month": months[0],
        "last_month": months[-1],
        "months": len(months),
        "months_with_data": len({row["month"] for row in rows}),
        "months_fetched_now": fetched,
        "missing_months": missing,
        "duplicate_rows_dropped": dropped,
        "rows": len(rows),
        "stations": len({(row["line"], row["station"]) for row in rows}),
        "lines": sorted({row["line"] for row in rows}),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    config = load_config(parser.parse_args().config)["subway_ridership"]
    key = os.environ.get(KEY_ENV, "").strip()

    months = period(config, date.today())
    if not key and any(not month_path(config, m).exists() for m in months):
        raise SystemExit(f"pipeline/.env 에 {KEY_ENV} 가 없습니다.")
    started = time.time()
    loaded, missing, fetched = load_months(config, months, month_fetcher(config, key))
    loaded, dropped = drop_duplicates(loaded)
    rows = to_rows(loaded)
    if not rows:
        raise SystemExit(
            f"{months[0]} ~ {months[-1]} 에 받은 자료가 없습니다. 기간을 확인하세요."
        )

    output = data_path(config["output"])
    write_parquet(rows, output)
    report = make_report(rows, months, missing, fetched, dropped)
    report_path = data_path(config["report"])
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"{report['months_with_data']}/{report['months']}달, {report['rows']}행, "
        f"역 {report['stations']}곳 → {output} ({time.time() - started:.0f}s)"
    )


if __name__ == "__main__":
    main()
