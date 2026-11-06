from datetime import date, datetime
from zoneinfo import ZoneInfo

import numpy as np

from foot_traffic import daily

ZONE = ZoneInfo("Asia/Seoul")
HOURS_PER_DAY = 24


def columns(rows: list[tuple[int, str, str]]) -> dict[str, np.ndarray]:
    """(센서, 자치구, slot_start) 행."""
    return {
        "sensor_code": np.array([r[0] for r in rows], dtype=np.int32),
        "district": np.array([r[1] for r in rows], dtype=object),
        "slot_start": np.array([r[2] for r in rows], dtype="datetime64[s]"),
    }


def test_to_libpq_url_drops_sqlalchemy_driver() -> None:
    assert (
        daily.to_libpq_url("postgresql+psycopg://u:p@h/db") == "postgresql://u:p@h/db"
    )
    assert daily.to_libpq_url("postgresql://u:p@h/db") == "postgresql://u:p@h/db"


def test_active_sensors_need_recent_rows_and_known_model() -> None:
    table = columns(
        [
            (1, "Jung-gu", "2026-11-05T10:00"),
            (2, "Jung-gu", "2026-11-01T10:00"),  # 끊긴 센서
            (3, "Mapo-gu", "2026-11-04T00:00"),  # 모델이 모르는 센서
            (4, "Mapo-gu", "2026-11-03T00:00"),  # 경계(3일 전 0시)
        ]
    )
    got = daily.active_sensors(table, date(2026, 11, 6), 3, known=[1, 2, 4])
    assert got == [1, 4]


def test_sensor_districts_use_latest_row() -> None:
    table = columns(
        [
            (1, "Old-gu", "2026-10-01T00:00"),
            (1, "Jung-gu", "2026-11-05T00:00"),
            (2, "Mapo-gu", "2026-11-05T00:00"),
        ]
    )
    assert daily.sensor_districts(table, [1, 2]) == ["Jung-gu", "Mapo-gu"]


def test_weather_arrays_align_next_hour_and_fill_missing_with_nan() -> None:
    day = date(2026, 11, 7)
    weather = daily.group_weather(
        [
            # 0시에 시작하는 행에는 1시 정시 예보가 붙는다.
            ("Jung-gu", datetime(2026, 11, 7, 1), 10.0, 0.0),
            ("Jung-gu", datetime(2026, 11, 8, 0), 3.0, None),  # 23시 행
            ("Mapo-gu", datetime(2026, 11, 7, 0), 99.0, 9.0),  # 전날 23시 행 몫
        ]
    )
    temp, rain = daily.weather_arrays(weather, ["Jung-gu", "Mapo-gu", "None-gu"], day)
    assert temp.shape == rain.shape == (3, HOURS_PER_DAY)
    assert temp[0, 0] == 10.0 and rain[0, 0] == 0.0
    assert temp[0, 23] == 3.0 and np.isnan(rain[0, 23])
    assert np.isnan(temp[1]).all() and np.isnan(temp[2]).all()


def test_records_map_sensor_order_and_hours() -> None:
    slots = np.array(
        ["2026-11-07T00:00", "2026-11-07T01:00", "2026-11-07T00:00"],
        dtype="datetime64[s]",
    )
    rows = {
        "sensor_code": np.array([3, 3, 7]),
        "slot_start": slots,
        "hour_of_day": np.array([0, 1, 0]),
    }
    temp = np.full((2, HOURS_PER_DAY), np.nan)
    temp[0, 1] = 12.5  # 센서 3, 1시 행
    temp[1, 0] = 4.0  # 센서 7, 0시 행
    rain = np.full((2, HOURS_PER_DAY), np.nan)
    trained = datetime(2026, 10, 25, 23, tzinfo=ZONE)
    created = datetime(2026, 11, 7, 7, 40, tzinfo=ZONE)
    got = daily.records(
        rows,
        np.array([100.0, 200.0, 50.0]),
        [3, 7],
        temp,
        rain,
        date(2026, 11, 7),
        trained,
        created,
        ZONE,
    )
    assert [r["temp_c"] for r in got] == [None, 12.5, 4.0]
    assert all(r["rain_mm"] is None for r in got)
    assert got[1]["slot_start"] == datetime(2026, 11, 7, 1, tzinfo=ZONE)
    assert got[2]["sensor_code"] == 7 and got[2]["foot_traffic"] == 50.0
    assert got[0]["issued_on"] == date(2026, 11, 7)


class FakeCursor:
    def __init__(self) -> None:
        self.many: list[tuple[str, list]] = []
        self.one: list[tuple[str, dict]] = []
        self.rowcount = 0

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def executemany(self, sql: str, rows: list) -> None:
        self.many.append((sql, rows))

    def execute(self, sql: str, params: dict) -> None:
        self.one.append((sql, params))
        self.rowcount = 5


class FakeConnection:
    def __init__(self) -> None:
        self.cur = FakeCursor()

    def cursor(self) -> FakeCursor:
        return self.cur


def test_write_upserts_then_deletes_old_forecasts() -> None:
    conn = FakeConnection()
    rows = [{"sensor_code": 1}, {"sensor_code": 2}]
    inserted, deleted = daily.write(conn, rows, date(2026, 8, 9))  # type: ignore[arg-type]
    assert (inserted, deleted) == (2, 5)
    assert "ON CONFLICT (sensor_code, issued_on, slot_start)" in conn.cur.many[0][0]
    assert conn.cur.one == [(daily.DELETE_OLD, {"cutoff": date(2026, 8, 9)})]
