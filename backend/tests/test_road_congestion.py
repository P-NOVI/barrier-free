from collections.abc import Callable

import httpx
import pytest
from fastapi.testclient import TestClient

from app import deps
from app.config import Settings
from app.deps import get_graph, get_realtime_congestion, get_road_congestion
from app.main import app
from app.repositories.sensor_repository import Sensor
from app.services.congestion_service import Reading, TtlCache, road_congestion
from core.congestion import congestion_level, edge_congestion
from core.graph import Graph

client = TestClient(app)

# 격자 길 간격(50m)보다 훨씬 좁아서 센서가 놓인 노드에 닿은 길만 걸린다.
RADIUS_M = 1.0
FULL_COUNT = 300.0
SETTINGS = Settings(
    sdot_api_key="test-key",
    congestion_full_count=FULL_COUNT,
    congestion_radius_m=RADIUS_M,
)


def position(graph: Graph, node: int) -> tuple[float, float]:
    return graph.nodes[node].lon, graph.nodes[node].lat


def edges_at(graph: Graph, node: int) -> set[int]:
    return {arc.edge_id for arc in graph.adjacency[node]}


def test_congestion_level_reaches_one_at_full_count() -> None:
    assert congestion_level(0, FULL_COUNT) == 0
    assert congestion_level(150, FULL_COUNT) == pytest.approx(0.5)
    assert congestion_level(900, FULL_COUNT) == 1


def test_roads_near_sensor_get_its_congestion(sample_graph: Graph) -> None:
    levels = edge_congestion(
        sample_graph,
        [(position(sample_graph, 0), 150), (position(sample_graph, 99), 0)],
        FULL_COUNT,
        RADIUS_M,
    )

    assert levels == dict.fromkeys(edges_at(sample_graph, 0), pytest.approx(0.5))


def test_road_between_two_sensors_gets_larger_congestion(sample_graph: Graph) -> None:
    levels = edge_congestion(
        sample_graph,
        [(position(sample_graph, 0), 150), (position(sample_graph, 1), 300)],
        FULL_COUNT,
        RADIUS_M,
    )
    (shared,) = edges_at(sample_graph, 0) & edges_at(sample_graph, 1)

    assert levels[shared] == 1
    assert set(levels) == edges_at(sample_graph, 0) | edges_at(sample_graph, 1)


def sdot_response(*rows: dict) -> httpx.Response:
    result = {"CODE": "INFO-000", "MESSAGE": "정상 처리되었습니다"}
    body = {"sDoTPeople": {"RESULT": result, "row": list(rows)}}
    return httpx.Response(200, json=body)


def row(serial: str, count: str) -> dict:
    return {
        "SERIAL": serial,
        "SENSING_TIME": "2026-11-03_14:48:00",
        "VISITOR_COUNT": count,
    }


def read_levels(
    graph: Graph,
    handler: Callable[[httpx.Request], httpx.Response],
    cache: TtlCache[dict[int, float]],
) -> tuple[dict[int, float], list[httpx.Request]]:
    received: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        received.append(request)
        return handler(request)

    levels = road_congestion(
        graph,
        {3032: Sensor(3032, position(graph, 0), "센서 주소")},
        SETTINGS,
        TtlCache[list[Reading]](60.0),
        cache,
        httpx.MockTransport(record),
    )
    return levels, received


def test_road_congestion_comes_from_sdot_and_is_cached(sample_graph: Graph) -> None:
    cache = TtlCache[dict[int, float]](60.0)
    first, received = read_levels(
        sample_graph, lambda _: sdot_response(row("3032", "300")), cache
    )
    second, again = read_levels(
        sample_graph, lambda _: sdot_response(row("3032", "0")), cache
    )

    assert first == dict.fromkeys(edges_at(sample_graph, 0), 1.0)
    assert len(received) == 1
    assert second == first
    assert again == []


def test_road_congestion_is_empty_and_cached_when_sdot_fails(
    sample_graph: Graph,
) -> None:
    cache = TtlCache[dict[int, float]](60.0)

    def fail(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    levels, received = read_levels(sample_graph, fail, cache)
    _, again = read_levels(sample_graph, fail, cache)

    assert levels == {}
    assert len(received) == 1
    assert again == []


def test_no_sdot_key_means_no_congestion(
    sample_graph: Graph, monkeypatch: pytest.MonkeyPatch
) -> None:
    def call_sdot(*args: object) -> dict[int, float]:
        pytest.fail("S-DoT 키가 없는데 S-DoT 를 불렀다")

    monkeypatch.setattr(deps, "load_sensors", lambda path: {})
    monkeypatch.setattr(deps, "road_congestion", call_sdot)

    levels = get_road_congestion(
        sample_graph,
        Settings(sdot_api_key=""),
        TtlCache[list[Reading]](60.0),
        TtlCache[dict[int, float]](60.0),
    )

    assert levels == {}


def route_via(graph: Graph, congestion: dict[int, float]) -> dict:
    """지금 출발하는 경로. 실시간 혼잡도를 congestion 으로 둔다."""
    app.dependency_overrides[get_graph] = lambda: graph
    app.dependency_overrides[get_realtime_congestion] = lambda: lambda: congestion
    try:
        response = client.post(
            "/api/route",
            json={"start": position(graph, 0), "goal": position(graph, 11)},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize(("crowded", "detour"), [(1, 10), (10, 1)])
def test_congestion_route_avoids_crowded_road(
    sample_graph: Graph, crowded: int, detour: int
) -> None:
    # 0 → 11 은 1 을 거치거나 10 을 거치는 같은 길이(100m) 두 갈래다.
    congestion = dict.fromkeys(edges_at(sample_graph, crowded), 1.0)

    body = route_via(sample_graph, congestion)

    # 1안이 붐비는 길로 가면 2안이 피하고, 1안이 이미 피했으면 2안은 없다.
    avoiding = body["alternative"] or body
    assert list(position(sample_graph, detour)) in avoiding["coordinates"]
    assert list(position(sample_graph, crowded)) not in avoiding["coordinates"]
    assert avoiding["busy_m"] == 0


def test_primary_route_ignores_congestion_and_reports_busy_length(
    sample_graph: Graph,
) -> None:
    # 혼잡도 없이 찾은 1안이 지나는 쪽을 붐비게 하면 1안은 그대로, 2안은 돌아간다.
    plain = route_via(sample_graph, {})
    assert plain["alternative"] is None
    crowded = 1 if list(position(sample_graph, 1)) in plain["coordinates"] else 10

    body = route_via(sample_graph, dict.fromkeys(edges_at(sample_graph, crowded), 1.0))

    assert body["coordinates"] == plain["coordinates"]
    assert body["busy_m"] > 0
    assert body["alternative"] is not None
    assert body["alternative"]["busy_m"] == 0
    assert body["alternative"]["coordinates"] != plain["coordinates"]


def test_no_alternative_when_it_only_avoids_lightly_busy_roads(
    sample_graph: Graph,
) -> None:
    # 1안이 지나는 쪽을 기준(0.5) 아래로만 붐비게 하면 2안은 돌아가도 붐비는 길 m 가
    # 줄지 않으므로 보여 주지 않는다.
    plain = route_via(sample_graph, {})
    crowded = 1 if list(position(sample_graph, 1)) in plain["coordinates"] else 10

    body = route_via(sample_graph, dict.fromkeys(edges_at(sample_graph, crowded), 0.3))

    assert body["busy_m"] == 0
    assert body["alternative"] is None
