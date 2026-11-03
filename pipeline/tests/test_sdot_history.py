import importlib.util
from datetime import datetime
from pathlib import Path

STEPS = Path(__file__).resolve().parents[1] / "steps"
NEW_HEADER = "모델번호,시리얼,측정시간,지역,자치구,행정동,방문자수,등록일"
OLD_HEADER = "기관 명,모델명,시리얼,서버타입,사이트명,방문자수,날짜,등록일자"
NO_SERIAL_HEADER = "측정시간,지역,자치구,행정동,방문자수,등록일"


def load_step(filename: str):
    spec = importlib.util.spec_from_file_location(filename[3:-3], STEPS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


history = load_step("06_build_sdot_history.py")


def new_row(
    serial: str,
    time: str,
    count: str,
    place=("parks", "Gu", "Dong"),
    registered: str = "2024-01-01 00:08:00",
) -> str:
    fields = ["SDOT001", serial, time, *place, count, registered]
    return ",".join(f'"{field}"' for field in fields)


def old_row(serial: str, time: str, count: str) -> str:
    fields = ["서울시", "SDOT001", serial, "00Original", "0000004015", count, time]
    return ",".join(f'"{field}"' for field in fields) + ',"2022-12-26 11:03:39","",""'


def write_week(
    path: Path, header: str, rows: list[str], encoding: str = "cp949"
) -> Path:
    path.write_text("\n".join([header, *rows]) + "\n", encoding=encoding)
    return path


def build(*paths: Path):
    return history.build_table(
        [history.week_table(history.read_week_file(path)) for path in paths]
    )


def test_reads_cp949_and_utf8_the_same(tmp_path: Path) -> None:
    rows = [new_row("00000003032", "2024-11-17_23:54:00", "157", ("시장", "구", "동"))]
    cp949 = write_week(tmp_path / "a.csv", NEW_HEADER, rows, "cp949")
    utf8 = write_week(tmp_path / "b.csv", NEW_HEADER, rows, "utf-8-sig")

    for path in (cp949, utf8):
        week = history.read_week_file(path)
        assert week.skip_reason is None
        assert week.codes == [3032]
        assert week.times == [datetime(2024, 11, 17, 23, 54)]
        assert week.counts == [157]
        assert week.places == [("시장", "구", "동")]


def test_reads_old_format(tmp_path: Path) -> None:
    path = write_week(
        tmp_path / "old.csv", OLD_HEADER, [old_row("4015", "202212261100", "150")]
    )

    week = history.read_week_file(path)

    assert week.codes == [4015]
    assert week.times == [datetime(2022, 12, 26, 11, 0)]
    assert week.counts == [150]
    assert week.places == [None]
    assert week.registered == [datetime(2022, 12, 26, 11, 3, 39)]


def test_skips_file_without_serial(tmp_path: Path) -> None:
    path = write_week(
        tmp_path / "noserial.csv",
        NO_SERIAL_HEADER,
        ['"2024-01-01_00:00:00","parks","Gu","Dong","0","2024-01-01 00:08:00"'],
    )

    week = history.read_week_file(path)

    assert week.skip_reason is not None
    assert week.codes == []
    assert week.total_rows == 1


def test_counts_unreadable_rows(tmp_path: Path) -> None:
    path = write_week(
        tmp_path / "bad.csv",
        NEW_HEADER,
        [
            new_row("00000003032", "2024-11-17_23:54:00", "10"),
            new_row("abc", "2024-11-17_23:54:00", "10"),
            new_row("00000003032", "어제", "10"),
            new_row("00000003032", "2024-11-17_23:54:00", "많음"),
            '"SDOT001","00000003032"',
        ],
    )

    week = history.read_week_file(path)

    assert week.codes == [3032]
    assert week.bad_rows == 4


def test_build_table_dedupes_and_sorts(tmp_path: Path) -> None:
    first = write_week(
        tmp_path / "w1.csv",
        NEW_HEADER,
        [
            new_row("00000003032", "2024-11-18_00:10:00", "20"),
            new_row("00000003032", "2024-11-17_23:50:00", "10"),
            new_row("00000003022", "2024-11-17_23:50:00", "5"),
            new_row("00000003022", "2024-11-17_23:50:00", "5"),
        ],
    )
    second = write_week(
        tmp_path / "w2.csv",
        NEW_HEADER,
        [new_row("00000003032", "2024-11-17_23:50:00", "11")],
    )

    table, stats = build(first, second)

    assert stats == {
        "rows_before_dedupe": 5,
        "duplicates_removed": 2,
        "conflicting_duplicates": 1,
    }
    assert table.column_names == [
        "sensor_code",
        "measured_at",
        "visitor_count",
        "region",
        "district",
        "dong",
        "source_file",
    ]
    rows = table.to_pylist()
    assert [(r["sensor_code"], r["measured_at"]) for r in rows] == [
        (3022, datetime(2024, 11, 17, 23, 50)),
        (3032, datetime(2024, 11, 17, 23, 50)),
        (3032, datetime(2024, 11, 18, 0, 10)),
    ]
    # 등록 시각이 같은 중복은 뒤에 읽은 값을 쓴다.
    assert rows[1]["visitor_count"] == 11
    assert rows[1]["source_file"] == "w2.csv"


def test_build_table_keeps_latest_registration(tmp_path: Path) -> None:
    week = write_week(
        tmp_path / "w1.csv",
        NEW_HEADER,
        [
            new_row(
                "00000003032",
                "2024-11-18_00:10:00",
                "99",
                registered="2024-11-19 03:00:00",
            ),
            new_row(
                "00000003032",
                "2024-11-18_00:10:00",
                "11",
                registered="2024-11-18 00:18:00",
            ),
            new_row("00000003022", "2024-11-18_00:10:00", "7", registered=""),
            new_row(
                "00000003022",
                "2024-11-18_00:10:00",
                "8",
                registered="2024-11-18 00:18:00",
            ),
        ],
    )

    table, stats = build(week)

    counts = {r["sensor_code"]: r["visitor_count"] for r in table.to_pylist()}
    # 늦게 등록된 값을 쓰고, 등록 시각이 없는 행은 있는 행보다 앞선 것으로 본다.
    assert counts == {3032: 99, 3022: 8}
    assert stats["conflicting_duplicates"] == 2


def test_skips_file_without_count(tmp_path: Path) -> None:
    path = write_week(
        tmp_path / "nocount.csv",
        "모델번호,시리얼,측정시간,지역,자치구,행정동,등록일",
        ['"SDOT001","00000003032","2024-01-01_00:00:00","p","G","D","2024-01-01"'],
    )

    week = history.read_week_file(path)

    assert week.skip_reason is not None
    assert week.codes == []


def test_build_table_of_nothing_is_empty() -> None:
    table, stats = history.build_table([])

    assert table.num_rows == 0
    assert stats["duplicates_removed"] == 0


def test_build_table_fills_places_of_old_format(tmp_path: Path) -> None:
    old = write_week(
        tmp_path / "old.csv",
        OLD_HEADER,
        [old_row("4015", "202212261100", "150"), old_row("9", "202212261100", "1")],
    )
    new = write_week(
        tmp_path / "new.csv",
        NEW_HEADER,
        [new_row("00000004015", "2023-01-02_00:00:00", "7", ("시장", "구", "동"))],
    )

    table, _ = build(old, new)

    by_code = {(r["sensor_code"], r["measured_at"].year): r for r in table.to_pylist()}
    assert by_code[(4015, 2022)]["region"] == "시장"
    assert by_code[(4015, 2022)]["dong"] == "동"
    # 신형 파일에 없는 센서는 채울 값이 없다.
    assert by_code[(9, 2022)]["region"] is None


def test_missing_weeks() -> None:
    names = [
        "S-DoT_WALK_2025.03.24-03.30.csv",
        "S-DoT_WALK_2025.04.07-04.13.csv",
        "S-DoT_WALK_2025.04.14-04.20.csv",
        "S-DoT_WALK_2025.04.21-04.27.csv",
        "S-DoT_WALK_2025.05.05-05.11.csv",
    ]

    assert history.missing_weeks(names) == ["2025-03-31", "2025-04-28"]
