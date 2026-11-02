"""S-DoT 과거 유동인구 주간 CSV 를 history.parquet 한 파일로 정리한다.

실행: pipeline/ 에서 uv run python steps/06_build_sdot_history.py
- 입력: 열린데이터광장 OA-15964 주간 CSV (raw/sdot/history/S-DoT_WALK_*.csv)
- 출력: interim/sdot/history.parquet 과 history_report.json
  열: sensor_code, measured_at, visitor_count, region, district, dong, source_file
  visitor_count 는 10분 구간의 합이다. 측정 시각은 원본 그대로 두고 10분 격자 맞추기는
  예측 모델 단계에서 한다.
처리
- 인코딩은 파일마다 감지한다(대부분 cp949, 일부 UTF-8).
- 구형(2022-12-26 주)과 신형 열 구성을 같은 형식으로 바꾼다. 구형에는 지역·자치구·
  행정동이 없어서 같은 센서의 가장 이른 신형 값으로 채운다.
- 시리얼 열이 없는 파일은 센서를 알 수 없어서 건너뛰고 보고서에 남긴다.
- (센서 코드, 측정 시각)이 같은 행은 하나만 남긴다. 값이 다르면 보고서에 개수를 남기고
  뒤에 읽은 값을 쓴다.
그래프(00~04 단계)와 관계가 없어서 run_all.py 에 넣지 않고 따로 실행한다.
"""

import argparse
import csv
import json
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from common import CONFIG_PATH, data_path, load_config, repo_path, require_files

SERIAL_COLUMN = "시리얼"
TIME_COLUMNS = ("측정시간", "날짜")
COUNT_COLUMN = "방문자수"
REGION_COLUMNS = {"region": "지역", "district": "자치구", "dong": "행정동"}
TIME_FORMAT = "%Y-%m-%d_%H:%M:%S"
# 구형 파일의 시각: 202212261100
COMPACT_TIME_LENGTH = 12
WEEK_PATTERN = re.compile(r"WALK_(\d{4})\.(\d{2})\.(\d{2})-")
WEEK_DAYS = 7
PARQUET_COMPRESSION = "zstd"
SCHEMA = pa.schema(
    [
        ("sensor_code", pa.int32()),
        ("measured_at", pa.timestamp("s")),
        ("visitor_count", pa.int32()),
        ("region", pa.string()),
        ("district", pa.string()),
        ("dong", pa.string()),
        ("source_file", pa.string()),
    ]
)


@dataclass
class WeekFile:
    """주간 CSV 하나를 읽은 결과. skip_reason 이 있으면 행은 쓰지 않는다."""

    name: str
    codes: list[int] = field(default_factory=list)
    times: list[datetime] = field(default_factory=list)
    counts: list[int] = field(default_factory=list)
    # 열이 없는 구형 파일은 None
    places: list[tuple[str, str, str] | None] = field(default_factory=list)
    bad_rows: int = 0
    total_rows: int = 0
    skip_reason: str | None = None


def detect_encoding(raw: bytes) -> str:
    """UTF-8 로 읽히면 UTF-8, 아니면 cp949."""
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        return "cp949"
    return "utf-8-sig"


def parse_time(text: str) -> datetime:
    if len(text) == COMPACT_TIME_LENGTH and text.isdigit():
        return datetime(
            int(text[0:4]),
            int(text[4:6]),
            int(text[6:8]),
            int(text[8:10]),
            int(text[10:12]),
        )
    return datetime.strptime(text, TIME_FORMAT)


def read_week_file(path: Path) -> WeekFile:
    raw = path.read_bytes()
    lines = raw.decode(detect_encoding(raw)).splitlines()
    week = WeekFile(name=path.name)
    if not lines:
        week.skip_reason = "빈 파일"
        return week
    header = next(csv.reader(lines[:1]))
    rows = list(csv.reader(lines[1:]))
    week.total_rows = len(rows)
    time_column = next((c for c in TIME_COLUMNS if c in header), None)
    if SERIAL_COLUMN not in header or time_column is None:
        week.skip_reason = f"{SERIAL_COLUMN} 열이 없음"
        return week
    serial_i, time_i = header.index(SERIAL_COLUMN), header.index(time_column)
    count_i = header.index(COUNT_COLUMN)
    place_i = [
        header.index(name) if name in header else None
        for name in REGION_COLUMNS.values()
    ]
    has_places = all(i is not None for i in place_i)
    # 주마다 측정 시각 문자열이 되풀이되므로 해석 결과를 재사용한다.
    parsed: dict[str, datetime] = {}
    for row in rows:
        try:
            code = int(row[serial_i])
            text = row[time_i]
            if text not in parsed:
                parsed[text] = parse_time(text)
            count = int(row[count_i])
            place = (
                (row[place_i[0]], row[place_i[1]], row[place_i[2]])
                if has_places
                else None
            )
        except (ValueError, IndexError):
            week.bad_rows += 1
            continue
        week.codes.append(code)
        week.times.append(parsed[text])
        week.counts.append(count)
        week.places.append(place)
    return week


def missing_weeks(names: list[str]) -> list[str]:
    """파일 이름의 주 시작일(월요일)이 7일 간격으로 이어지지 않은 곳의 빠진 주."""
    starts = sorted(
        date(int(m[1]), int(m[2]), int(m[3]))
        for name in names
        if (m := WEEK_PATTERN.search(name))
    )
    missing = []
    for before, after in zip(starts, starts[1:]):
        day = before + timedelta(days=WEEK_DAYS)
        while day < after:
            missing.append(day.isoformat())
            day += timedelta(days=WEEK_DAYS)
    return missing


def build_table(weeks: list[WeekFile]) -> tuple[pa.Table, dict[str, int]]:
    """읽은 주들을 하나로 합쳐 중복을 없애고 측정 시각 순으로 정렬한다."""
    # 구형 파일의 지역은 같은 센서의 가장 이른 신형 값으로 채운다.
    first_place: dict[int, tuple[str, str, str]] = {}
    for week in weeks:
        for code, place in zip(week.codes, week.places):
            if place is not None and code not in first_place:
                first_place[code] = place

    columns: dict[str, list[Any]] = {name: [] for name in SCHEMA.names}
    for week in weeks:
        places = [
            place or first_place.get(code)
            for code, place in zip(week.codes, week.places)
        ]
        columns["sensor_code"] += week.codes
        columns["measured_at"] += week.times
        columns["visitor_count"] += week.counts
        for i, key in enumerate(REGION_COLUMNS):
            columns[key] += [place[i] if place else None for place in places]
        columns["source_file"] += [week.name] * len(week.codes)
    table = pa.table(columns, schema=SCHEMA)

    rows = table.num_rows
    indexed = table.append_column("_row", pa.array(range(rows), type=pa.int64()))
    groups = indexed.group_by(["sensor_code", "measured_at"], use_threads=False)
    unique = groups.aggregate(
        [("_row", "max"), ("visitor_count", "min"), ("visitor_count", "max")]
    )
    conflicts = pc.sum(
        pc.not_equal(unique["visitor_count_min"], unique["visitor_count_max"])
    ).as_py()
    deduped = table.take(unique["_row_max"]).sort_by(
        [("measured_at", "ascending"), ("sensor_code", "ascending")]
    )
    stats = {
        "rows_before_dedupe": rows,
        "duplicates_removed": rows - deduped.num_rows,
        "conflicting_duplicates": conflicts or 0,
    }
    return deduped, stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    config = load_config(parser.parse_args().config)["sdot_history"]
    source = data_path(config["source_dir"])
    output = data_path(config["output"])
    report_path = data_path(config["report"])
    sensors_path = repo_path(config["sensors"])
    require_files(source, sensors_path)

    started = time.time()
    files = sorted(source.glob("S-DoT_WALK_*.csv"))
    if not files:
        raise SystemExit(f"주간 CSV(S-DoT_WALK_*.csv)가 없습니다: {source}")
    weeks = []
    for i, path in enumerate(files, 1):
        weeks.append(read_week_file(path))
        print(f"\r읽는 중 {i}/{len(files)}", end="", flush=True)
    print()

    used = [week for week in weeks if week.skip_reason is None]
    table, stats = build_table(used)
    output.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, output, compression=PARQUET_COMPRESSION)

    known = {
        sensor["code"]
        for sensor in json.loads(sensors_path.read_text(encoding="utf-8"))["sensors"]
    }
    codes = set(table["sensor_code"].to_pylist())
    times = table["measured_at"]
    report = {
        "files_total": len(files),
        "files_used": len(used),
        "files_skipped": [
            {"name": w.name, "reason": w.skip_reason, "rows": w.total_rows}
            for w in weeks
            if w.skip_reason
        ],
        "missing_weeks": missing_weeks([w.name for w in weeks]),
        "bad_rows": {w.name: w.bad_rows for w in used if w.bad_rows},
        **stats,
        "rows": table.num_rows,
        "sensors": len(codes),
        "sensors_without_location": sorted(codes - known),
        "first_measured_at": pc.min(times).as_py().isoformat(),
        "last_measured_at": pc.max(times).as_py().isoformat(),
        "weeks": [
            {"name": w.name, "rows": len(w.codes), "sensors": len(set(w.codes))}
            for w in used
        ],
        "zero_visitor_share": round(
            pc.sum(pc.equal(table["visitor_count"], 0)).as_py() / table.num_rows, 4
        ),
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    counts = Counter(w.skip_reason for w in weeks if w.skip_reason)
    print(
        f"행 {table.num_rows:,}, 센서 {len(codes)}개, 파일 {len(used)}/{len(files)} "
        f"(건너뜀 {dict(counts) or '없음'}), 중복 제거 {stats['duplicates_removed']:,} "
        f"→ {output} ({output.stat().st_size / 1e6:.0f} MB, "
        f"{time.time() - started:.0f}s)",
        flush=True,
    )
    print(f"보고서 {report_path}", flush=True)


if __name__ == "__main__":
    main()
