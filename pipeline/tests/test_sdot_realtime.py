import importlib.util
from datetime import datetime
from pathlib import Path

import pyarrow as pa

STEPS = Path(__file__).resolve().parents[1] / "steps"


def load_step(filename: str):
    spec = importlib.util.spec_from_file_location(filename[3:-3], STEPS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


realtime = load_step("16_export_sdot_realtime.py")


def test_to_libpq_url_drops_sqlalchemy_driver() -> None:
    assert (
        realtime.to_libpq_url("postgresql+psycopg://u:p@localhost:5432/db")
        == "postgresql://u:p@localhost:5432/db"
    )
    assert (
        realtime.to_libpq_url("postgresql://u:p@host:6543/db")
        == "postgresql://u:p@host:6543/db"
    )


def test_to_table_matches_history_schema() -> None:
    rows = [
        (3009, datetime(2026, 10, 25, 23, 58), 251, "market", "Jung-gu", "Myeong"),
        (3010, datetime(2026, 10, 26, 0, 8), 0, None, None, None),
    ]
    table = realtime.to_table(rows, "collector_db")
    assert table.schema == realtime.SCHEMA
    assert table["measured_at"].type == pa.timestamp("ms")
    assert table["measured_at"].to_pylist()[0] == datetime(2026, 10, 25, 23, 58)
    assert table["source_file"].to_pylist() == ["collector_db"] * 2
    assert table["district"].null_count == 1


def test_make_report_handles_empty_and_rows() -> None:
    assert realtime.make_report(realtime.to_table([], "x")) == {
        "rows": 0,
        "sensors": 0,
    }
    rows = [(1, datetime(2026, 10, 26, 0, 8), 5, None, "Jung-gu", None)]
    report = realtime.make_report(realtime.to_table(rows, "x"))
    assert report["rows"] == 1
    assert report["first_measured_at"] == "2026-10-26T00:08:00"
