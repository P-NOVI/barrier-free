from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.collector.models import CollectorBase, FootTrafficForecast
from app.config import Settings
from app.deps import get_forecast_congestion, get_graph, get_realtime_congestion
from app.main import app
from app.repositories.sensor_repository import Sensor
from app.routers.routes import depart_slot
from app.services.congestion_service import KST
from app.services.forecast_congestion_service import (
    ForecastCache,
    forecast_congestion,
    latest_forecasts,
)
from core.graph import Graph

client = TestClient(app)

NOW = datetime(2026, 11, 6, 14, 25, tzinfo=KST)
SLOT = datetime(2026, 11, 7, 15, tzinfo=KST)
SETTINGS = Settings(
    congestion_full_count=300.0, congestion_radius_m=1.0, forecast_bins_per_hour=6
)


# --- 출발 시각 ---


def test_depart_slot_floors_to_hour_and_keeps_now_as_none() -> None:
    assert depart_slot(None, NOW, 3) is None
    assert depart_slot(datetime(2026, 11, 7, 15, 40, tzinfo=KST), NOW, 3) == SLOT
    # 시간대가 없으면 한국 시각으로 본다.
    assert depart_slot(datetime(2026, 11, 7, 15), NOW, 3) == SLOT


@pytest.mark.parametrize(
    "depart",
    [
        datetime(2026, 11, 6, 14, 0, tzinfo=KST),  # 지금 시
        datetime(2026, 11, 8, 23, 0, tzinfo=KST),  # 모레 23시
    ],
)
def test_depart_slot_accepts_now_hour_to_day_after_tomorrow(depart: datetime) -> None:
    assert depart_slot(depart, NOW, 3) == depart


@pytest.mark.parametrize(
    "depart",
    [
        datetime(2026, 11, 6, 13, 59, tzinfo=KST),  # 지난 시
        datetime(2026, 11, 9, 0, 0, tzinfo=KST),  # 모레 뒤
    ],
)
def test_depart_slot_rejects_past_and_after_day_after_tomorrow(
    depart: datetime,
) -> None:
    with pytest.raises(ValueError):
        depart_slot(depart, NOW, 3)


# --- 예측 읽기 ---


@pytest.fixture
def engine():
    engine = create_engine("sqlite://", poolclass=StaticPool)
    CollectorBase.metadata.create_all(engine)
    return engine


def add_forecast(engine, code: int, issued: date, value: float) -> None:
    with Session(engine) as session:
        session.add(
            FootTrafficForecast(
                sensor_code=code,
                issued_on=issued,
                slot_start=SLOT,
                foot_traffic=value,
                model_trained_until=NOW,
                created_at=NOW,
            )
        )
        session.commit()


def test_latest_forecasts_use_newest_issue_up_to_today(engine) -> None:
    add_forecast(engine, 1, date(2026, 11, 5), 100.0)
    add_forecast(engine, 1, date(2026, 11, 6), 200.0)
    add_forecast(engine, 1, date(2026, 11, 7), 999.0)  # 오늘 뒤에 예측한 것
    add_forecast(engine, 2, date(2026, 11, 5), 50.0)

    with Session(engine) as session:
        assert latest_forecasts(session, SLOT, date(2026, 11, 6)) == {
            1: 200.0,
            2: 50.0,
        }
        assert latest_forecasts(session, SLOT, date(2026, 11, 5)) == {
            1: 100.0,
            2: 50.0,
        }


def test_forecast_congestion_divides_hourly_count_and_caches(
    engine, sample_graph: Graph
) -> None:
    node = sample_graph.nodes[1]
    sensors = {7: Sensor(7, (node.lon, node.lat), "")}
    # 900명/시간 = 10분 150명 = 혼잡도 0.5
    add_forecast(engine, 7, date(2026, 11, 6), 900.0)
    add_forecast(engine, 8, date(2026, 11, 6), 900.0)  # 위치를 모르는 센서
    cache = ForecastCache(600)

    levels = forecast_congestion(
        engine, sample_graph, sensors, SETTINGS, SLOT, date(2026, 11, 6), cache
    )

    near = {arc.edge_id for arc in sample_graph.adjacency[1]}
    assert set(levels) == near
    assert all(level == pytest.approx(0.5) for level in levels.values())
    assert cache.get(SLOT) == levels


def test_forecast_congestion_is_empty_when_db_fails(sample_graph: Graph) -> None:
    broken = create_engine("sqlite://", poolclass=StaticPool)  # 표가 없다
    levels = forecast_congestion(
        broken, sample_graph, {}, SETTINGS, SLOT, date(2026, 11, 6), ForecastCache(60)
    )
    assert levels == {}


# --- 경로 API ---


def post(graph: Graph, **body) -> tuple[int, dict, list]:
    """경로 요청. 반환: (상태 코드, 응답, 예측을 부른 시각들)"""
    asked: list[datetime] = []

    def forecast(slot: datetime) -> dict[int, float]:
        asked.append(slot)
        return {}

    def realtime() -> dict[int, float]:
        raise AssertionError("출발 시각을 고르면 실시간 혼잡도를 부르지 않는다")

    app.dependency_overrides[get_graph] = lambda: graph
    app.dependency_overrides[get_forecast_congestion] = lambda: forecast
    app.dependency_overrides[get_realtime_congestion] = lambda: realtime
    start = [graph.nodes[0].lon, graph.nodes[0].lat]
    goal = [graph.nodes[11].lon, graph.nodes[11].lat]
    try:
        response = client.post(
            "/api/route", json={"start": start, "goal": goal, **body}
        )
    finally:
        app.dependency_overrides.clear()
    return response.status_code, response.json(), asked


def test_route_with_depart_at_uses_forecast_of_that_hour(sample_graph: Graph) -> None:
    depart = datetime.now(KST).replace(minute=30, second=0, microsecond=0)
    status, body, asked = post(sample_graph, depart_at=depart.isoformat())

    assert status == 200
    assert asked == [depart.replace(minute=0)]
    # 예측이 비어 있으면 1안만 나온다.
    assert body["alternative"] is None
    assert body["busy_m"] == 0


def test_route_rejects_depart_at_out_of_range(sample_graph: Graph) -> None:
    past = datetime(2020, 1, 1, 9, tzinfo=KST)
    status, body, asked = post(sample_graph, depart_at=past.isoformat())

    assert status == 422
    assert body["detail"]["reason"] == "invalid_depart_at"
    assert asked == []
