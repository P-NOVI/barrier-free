"""출발 시각의 예측 유동인구를 길별 혼잡도(0~1)로 바꾼다.

예측은 ml 의 매일 배치(foot_traffic.daily)가 수집 DB 의 foot_traffic_forecasts 에
쌓는다. 같은 시각을 사흘 연속 예측하므로, 오늘까지 예측한 것 중 가장 최근 것을 쓴다.
예측(명/시간)을 forecast_bins_per_hour 로 나눠 10분 유동인구로 바꾼 뒤, 실시간과 같은
기준(congestion_full_count, congestion_radius_m)으로 혼잡도를 만든다.
"""

from collections.abc import Mapping
from datetime import date, datetime

from sqlalchemy import Engine, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.collector.models import FootTrafficForecast
from app.config import Settings
from app.repositories.sensor_repository import Sensor
from app.services.weather_service import KeyedTtlCache
from core.congestion import edge_congestion
from core.graph import Graph

ForecastCache = KeyedTtlCache[datetime, dict[int, float]]


def latest_forecasts(session: Session, slot: datetime, today: date) -> dict[int, float]:
    """센서 코드 → slot 시작 한 시간의 예측 유동인구(명/시간).

    센서마다 issued_on 이 today 이하인 것 중 가장 최근 예측을 쓴다.
    """
    latest = (
        select(
            FootTrafficForecast.sensor_code,
            func.max(FootTrafficForecast.issued_on).label("issued_on"),
        )
        .where(
            FootTrafficForecast.slot_start == slot,
            FootTrafficForecast.issued_on <= today,
        )
        .group_by(FootTrafficForecast.sensor_code)
        .subquery()
    )
    rows = session.execute(
        select(FootTrafficForecast.sensor_code, FootTrafficForecast.foot_traffic)
        .join(
            latest,
            (FootTrafficForecast.sensor_code == latest.c.sensor_code)
            & (FootTrafficForecast.issued_on == latest.c.issued_on),
        )
        .where(FootTrafficForecast.slot_start == slot)
    ).all()
    return {int(code): float(value) for code, value in rows}


def forecast_congestion(
    engine: Engine,
    graph: Graph,
    sensors: Mapping[int, Sensor],
    settings: Settings,
    slot: datetime,
    today: date,
    cache: ForecastCache,
) -> dict[int, float]:
    """slot 시작 한 시간의 길별 혼잡도. edge_id → 0~1.

    수집 DB를 읽지 못하면 빈 값(혼잡 없음)이다. 빈 값도 캐시해, 장애 동안 경로
    요청마다 DB를 기다리지 않게 한다.
    """
    levels = cache.get(slot)
    if levels is not None:
        return levels
    try:
        with Session(engine) as session:
            counts = latest_forecasts(session, slot, today)
    except SQLAlchemyError:
        counts = {}
    levels = edge_congestion(
        graph,
        [
            (sensors[code].position, count / settings.forecast_bins_per_hour)
            for code, count in counts.items()
            # 위치 파일에 없는 센서는 길에 붙일 수 없다.
            if code in sensors
        ],
        settings.congestion_full_count,
        settings.congestion_radius_m,
    )
    cache.set(slot, levels)
    return levels
