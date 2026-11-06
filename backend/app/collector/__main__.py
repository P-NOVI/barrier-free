"""유동인구·날씨를 한 번 받아 수집 DB에 넣고 끝난다. GitHub Actions 가 10분마다 부른다.

실행: backend/ 에서 uv run python -m app.collector
필요한 환경변수: COLLECTOR_DATABASE_URL, SDOT_API_KEY, KMA_API_KEY
한 작업이 실패해도 나머지는 하고, 실패가 있으면 종료 코드 1로 끝난다.
"""

import sys
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.collector.sdot import collect_sdot
from app.collector.store import collector_engine
from app.collector.weather import (
    collect_weather_daily,
    collect_weather_now,
    district_grids,
)
from app.config import Settings, get_settings
from app.repositories.sensor_repository import load_sensors
from app.services.congestion_service import CongestionError, create_sdot_client
from app.services.weather_service import (
    KST,
    ItemCache,
    KeyedTtlCache,
    WeatherError,
    create_kma_client,
)

FAILURES = (CongestionError, WeatherError, SQLAlchemyError)


def run(name: str, session: Session, job: Callable[[], int]) -> bool:
    """작업 하나를 하고 커밋한다. 실패하면 되돌리고 False."""
    try:
        count = job()
        session.commit()
    except FAILURES as error:
        session.rollback()
        # 예외 문구에 접속 주소·키가 섞일 수 있어 종류만 남긴다.
        print(f"{name}: 실패 ({type(error).__name__})")
        return False
    print(f"{name}: {count}행 추가")
    return True


def collect(session: Session, settings: Settings, now: datetime) -> bool:
    ok = True
    with create_sdot_client(settings) as client:
        ok &= run(
            "유동인구", session, lambda: collect_sdot(session, client, settings, now)
        )
    grids = district_grids(
        session,
        load_sensors(settings.sensors_path),
        now - timedelta(days=settings.collector_district_days),
    )
    cache: ItemCache = KeyedTtlCache(settings.kma_cache_ttl_s)
    with create_kma_client(settings) as client:
        ok &= run(
            "실시간 날씨",
            session,
            lambda: collect_weather_now(session, client, grids, settings, now, cache),
        )
        ok &= run(
            "하루치 날씨",
            session,
            lambda: collect_weather_daily(session, client, grids, settings, now, cache),
        )
    return ok


def main() -> int:
    settings = get_settings()
    database_url = settings.collector_database_url.get_secret_value()
    if not database_url:
        print("COLLECTOR_DATABASE_URL 이 비어 있습니다.")
        return 1
    try:
        engine = collector_engine(database_url, settings.collector_connect_timeout_s)
    except SQLAlchemyError as error:
        print(f"수집 DB 연결 실패 ({type(error).__name__})")
        return 1
    with Session(engine) as session:
        ok = collect(session, settings, datetime.now(KST))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
