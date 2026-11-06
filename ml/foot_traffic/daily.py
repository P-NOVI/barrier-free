"""매일 유동인구 예측 배치. 오늘·내일·모레를 예측해 수집 DB에 저장한다.

실행: ml/ 에서 uv run python -m foot_traffic.daily [--date YYYY-MM-DD]
- 먼저 pipeline 16 → 13 단계로 학습셋을 갱신해 둔다.
  GitHub Actions(forecast-daily.yml)가 유동인구 수집 뒤에 차례로 돌린다.
- 입력: 학습셋(walk_forward.training_set), 달력, 서비스 모델·메타(DATA_DIR),
  수집 DB(ml/.env 의 COLLECTOR_DATABASE_URL)의 weather_daily(구별 단기예보).
- 출력: 수집 DB 의 foot_traffic_forecasts(backend/app/collector/models.py).
  (센서, 예측한 날, 시각)이 같으면 덮어쓴다. retention_days 가 지난 예측은 지운다.
- 대상: 배치 날 기준 최근 active_days 일 안에 학습셋 행이 있는 센서(모델이 아는 센서만).
  값이 끊긴 센서는 예전 수준으로 예측되므로 뺀다.
- 날씨: 배치 날 weather_issue_hour 시 발표분(없으면 그 앞의 가장 최근 발표분). 한 시간
  행(h 시 시작)에는 h+1 시 정시 예보를 붙인다(13 단계 학습셋과 같다). 없는 칸은 비운다.
"""

import argparse
import os
import sys
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import psycopg

from foot_traffic.common import CONFIG_PATH, data_path, load_config
from foot_traffic.data import Columns, load_columns
from foot_traffic.forecast import forecast, load_service
from foot_traffic.recent import HOURS_PER_DAY

URL_ENV = "COLLECTOR_DATABASE_URL"
# SQLAlchemy 주소(postgresql+psycopg://)를 psycopg 가 읽는 주소로 바꾼다.
DRIVER_PREFIXES = ("postgresql+psycopg://", "postgres+psycopg://")
HOUR = timedelta(hours=1)
# 표 이름·열 이름은 backend/app/collector/models.py 와 같다.
WEATHER_QUERY = """
SELECT district, forecast_at AT TIME ZONE %(timezone)s, temp_c, rain_mm
FROM weather_daily
WHERE issued_at = (
    SELECT max(issued_at) FROM weather_daily WHERE issued_at <= %(issued)s
)
"""
UPSERT = """
INSERT INTO foot_traffic_forecasts (
    sensor_code, issued_on, slot_start, foot_traffic, temp_c, rain_mm,
    model_trained_until, created_at
) VALUES (
    %(sensor_code)s, %(issued_on)s, %(slot_start)s, %(foot_traffic)s, %(temp_c)s,
    %(rain_mm)s, %(model_trained_until)s, %(created_at)s
)
ON CONFLICT (sensor_code, issued_on, slot_start) DO UPDATE SET
    foot_traffic = EXCLUDED.foot_traffic,
    temp_c = EXCLUDED.temp_c,
    rain_mm = EXCLUDED.rain_mm,
    model_trained_until = EXCLUDED.model_trained_until,
    created_at = EXCLUDED.created_at
"""
DELETE_OLD = "DELETE FROM foot_traffic_forecasts WHERE issued_on < %(cutoff)s"

# 구 → (h+1 시 정시, 한국 시각) → (기온, 강수)
Weather = dict[str, dict[datetime, tuple[float | None, float | None]]]


def to_libpq_url(url: str) -> str:
    """SQLAlchemy 드라이버 표시를 뺀 PostgreSQL 주소."""
    for prefix in DRIVER_PREFIXES:
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix) :]
    return url


def active_sensors(
    columns: Columns, day: date, active_days: int, known: Sequence[int]
) -> list[int]:
    """day 전 active_days 일 안에 학습셋 행이 있고, 모델이 아는 센서."""
    since = np.datetime64(day - timedelta(days=active_days), "s")
    recent = columns["sensor_code"][columns["slot_start"] >= since]
    return sorted(set(int(code) for code in recent) & set(int(c) for c in known))


def sensor_districts(columns: Columns, sensors: Sequence[int]) -> list[str]:
    """센서마다 가장 최근 행의 자치구."""
    districts = []
    for sensor in sensors:
        own = np.flatnonzero(columns["sensor_code"] == sensor)
        latest = own[np.argmax(columns["slot_start"][own])]
        districts.append(str(columns["district"][latest]))
    return districts


def group_weather(
    rows: Sequence[tuple[str, datetime, float | None, float | None]],
) -> Weather:
    """DB 행 (구, 예보 시각(한국, 시간대 없음), 기온, 강수) → 구별 시각별 값."""
    weather: Weather = {}
    for district, moment, temp, rain in rows:
        weather.setdefault(district, {})[moment] = (temp, rain)
    return weather


def weather_arrays(
    weather: Weather, districts: Sequence[str], day: date
) -> tuple[np.ndarray, np.ndarray]:
    """센서별 (기온, 강수) 배열. 모양 (센서 수, 24). h 열은 h+1 시 정시 예보다."""
    temp = np.full((len(districts), HOURS_PER_DAY), np.nan)
    rain = np.full((len(districts), HOURS_PER_DAY), np.nan)
    start = datetime.combine(day, time())
    for i, district in enumerate(districts):
        hours = weather.get(district, {})
        for h in range(HOURS_PER_DAY):
            value = hours.get(start + (h + 1) * HOUR)
            if value is None:
                continue
            if value[0] is not None:
                temp[i, h] = value[0]
            if value[1] is not None:
                rain[i, h] = value[1]
    return temp, rain


def optional(value: float) -> float | None:
    return None if np.isnan(value) else float(value)


def records(
    rows: Columns,
    pred: np.ndarray,
    sensors: Sequence[int],
    temp: np.ndarray,
    rain: np.ndarray,
    issued_on: date,
    trained_until: datetime,
    created_at: datetime,
    zone: ZoneInfo,
) -> list[dict[str, Any]]:
    """예측 한 번(하루) → foot_traffic_forecasts 행.

    rows·pred 는 forecast() 결과이고, temp·rain 은 sensors 순서의 (센서 수, 24)다.
    """
    order = {int(code): i for i, code in enumerate(sensors)}
    result = []
    for code, slot, hour, value in zip(
        rows["sensor_code"], rows["slot_start"], rows["hour_of_day"], pred
    ):
        i = order[int(code)]
        h = int(hour)
        result.append(
            {
                "sensor_code": int(code),
                "issued_on": issued_on,
                "slot_start": slot.astype("datetime64[s]").item().replace(tzinfo=zone),
                "foot_traffic": float(value),
                "temp_c": optional(temp[i, h]),
                "rain_mm": optional(rain[i, h]),
                "model_trained_until": trained_until,
                "created_at": created_at,
            }
        )
    return result


def write(
    conn: psycopg.Connection, rows: list[dict[str, Any]], cutoff: date
) -> tuple[int, int]:
    """덮어써 넣고 오래된 예측을 지운다. 반환: (넣은 행, 지운 행)"""
    with conn.cursor() as cursor:
        cursor.executemany(UPSERT, rows)
        cursor.execute(DELETE_OLD, {"cutoff": cutoff})
        deleted = cursor.rowcount
    return len(rows), deleted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--date", help="배치 날짜(한국, YYYY-MM-DD). 없으면 오늘")
    args = parser.parse_args()
    config = load_config(args.config)
    daily = config["daily"]
    zone = ZoneInfo(daily["timezone"])
    now = datetime.now(zone)
    issued_on = date.fromisoformat(args.date) if args.date else now.date()
    url = os.environ.get(URL_ENV, "").strip().strip('"')
    if not url:
        print(f"ml/.env 의 {URL_ENV} 가 비어 있습니다.")
        return 1

    booster, meta = load_service(config)
    columns = load_columns(data_path(config["walk_forward"]["training_set"]))
    calendar = data_path(config["data"]["calendar"])
    sensors = active_sensors(
        columns, issued_on, daily["active_days"], meta["vocab"]["sensor_code"]
    )
    if not sensors:
        print(f"최근 {daily['active_days']}일 안에 실측이 있는 센서가 없습니다.")
        return 1
    districts = sensor_districts(columns, sensors)
    trained_until = datetime.fromisoformat(meta["train_last_slot"]).replace(tzinfo=zone)
    issued_at = datetime.combine(
        issued_on, time(daily["weather_issue_hour"]), tzinfo=zone
    )
    try:
        with psycopg.connect(
            to_libpq_url(url), connect_timeout=daily["connect_timeout_s"]
        ) as conn:
            weather = group_weather(
                conn.execute(
                    WEATHER_QUERY,
                    {"timezone": daily["timezone"], "issued": issued_at},
                ).fetchall()
            )
            rows: list[dict[str, Any]] = []
            for offset in range(daily["days"]):
                day = issued_on + timedelta(days=offset)
                temp, rain = weather_arrays(weather, districts, day)
                try:
                    part, pred = forecast(
                        columns,
                        calendar,
                        booster,
                        meta,
                        config,
                        sensors,
                        day.isoformat(),
                        temp,
                        rain,
                    )
                except ValueError as error:
                    print(f"{day} 예측 실패: {error}")
                    return 1
                rows += records(
                    part,
                    pred,
                    sensors,
                    temp,
                    rain,
                    issued_on,
                    trained_until,
                    now,
                    zone,
                )
                print(f"{day}: 센서 {len(sensors)}개, 합계 {pred.sum():,.0f}명")
            cutoff = issued_on - timedelta(days=daily["retention_days"])
            inserted, deleted = write(conn, rows, cutoff)
    except psycopg.Error as error:
        # 예외 문구에 접속 주소가 섞일 수 있어 종류만 남긴다.
        print(f"수집 DB 실패 ({type(error).__name__})")
        return 1
    filled = sum(row["temp_c"] is not None for row in rows)
    print(
        f"예측 {inserted:,}행 저장(날씨 있는 행 {filled:,}), "
        f"오래된 예측 {deleted:,}행 삭제"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
