from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.deps import get_db_session, get_graph, get_report_finder
from app.main import app
from app.models import Report, ReportReview, utc_now
from app.repositories.report_repository import list_reviewable_reports
from app.routers.routes import reports_on_route
from core.graph import Graph


@pytest.fixture
def client(db_session: Session, sample_graph: Graph) -> Iterator[TestClient]:
    app.dependency_overrides[get_db_session] = lambda: db_session
    app.dependency_overrides[get_graph] = lambda: sample_graph
    yield TestClient(app)
    app.dependency_overrides.clear()


def add_report(db_session: Session, edge_id: int = 1, **fields: object) -> Report:
    values = {
        "kind": "curb",
        "blocked": False,
        "status": "approved",
        "photo_name": "a.jpg",
        "description": "턱이 높아요",
        "lon": 126.9779,
        "lat": 37.5663,
        "edge_id": edge_id,
        "expires_at": utc_now() + timedelta(days=30),
        **fields,
    }
    report = Report(**values)
    db_session.add(report)
    db_session.commit()
    return report


def route_request(sample_graph: Graph) -> dict:
    goal = len(sample_graph.nodes) - 1
    start, end = sample_graph.nodes[0], sample_graph.nodes[goal]
    return {"start": [start.lon, start.lat], "goal": [end.lon, end.lat]}


def route_edge_ids(client: TestClient, sample_graph: Graph) -> frozenset[int]:
    """경로가 지나는 길을 알아내려고, 제보 찾는 함수가 받은 edge_id 를 가로챈다."""
    seen: list[frozenset[int]] = []

    def spy(edge_ids: frozenset[int]) -> list[Report]:
        seen.append(edge_ids)
        return []

    app.dependency_overrides[get_report_finder] = lambda: spy
    response = client.post("/api/route", json=route_request(sample_graph))
    assert response.status_code == 200
    return seen[0]


def test_route_passes_its_edge_ids_to_the_finder(
    client: TestClient, sample_graph: Graph
) -> None:
    edge_ids = route_edge_ids(client, sample_graph)

    assert edge_ids


def route_coordinates(client: TestClient, sample_graph: Graph) -> list[list[float]]:
    response = client.post("/api/route", json=route_request(sample_graph))
    assert response.status_code == 200
    return response.json()["coordinates"]


def use_real_finder(db_session: Session) -> None:
    app.dependency_overrides[get_report_finder] = lambda: (
        lambda edge_ids: list_reviewable_reports(db_session, edge_ids, utc_now())
    )


def test_route_lists_only_reviewable_reports_on_its_edges(
    client: TestClient, db_session: Session, sample_graph: Graph
) -> None:
    on_route = sorted(route_edge_ids(client, sample_graph))[0]
    off_route = max(route_edge_ids(client, sample_graph)) + 10_000
    lon, lat = route_coordinates(client, sample_graph)[0]
    at_route = {"lon": lon, "lat": lat}
    shown = add_report(db_session, on_route, kind="damage", **at_route)
    add_report(db_session, on_route, status="pending", **at_route)
    add_report(db_session, on_route, status="rejected", **at_route)
    add_report(db_session, on_route, status="resolved", **at_route)
    add_report(db_session, on_route, kind="construction", blocked=True, **at_route)
    add_report(
        db_session, on_route, expires_at=utc_now() - timedelta(days=1), **at_route
    )
    add_report(db_session, off_route, **at_route)
    use_real_finder(db_session)

    response = client.post("/api/route", json=route_request(sample_graph))

    assert response.status_code == 200
    assert response.json()["reports"] == [
        {
            "id": shown.id,
            "kind": "damage",
            "description": "턱이 높아요",
            "position": [lon, lat],
        }
    ]


def test_route_drops_report_on_a_part_of_the_edge_it_does_not_pass(
    client: TestClient, db_session: Session, sample_graph: Graph
) -> None:
    on_route = sorted(route_edge_ids(client, sample_graph))[0]
    lon, lat = route_coordinates(client, sample_graph)[0]
    # 같은 길 번호지만 경로에서 100m 넘게 떨어진 곳(경로가 지나지 않는 구간)
    add_report(db_session, on_route, lon=lon, lat=lat + 0.001)
    use_real_finder(db_session)

    response = client.post("/api/route", json=route_request(sample_graph))

    assert response.status_code == 200
    assert response.json()["reports"] == []


def line_report(lon: float, lat: float) -> Report:
    return Report(id=1, kind="curb", description=None, lon=lon, lat=lat)


# 동서로 곧게 뻗은 약 85m 경로
LINE = [(126.9779, 37.5663), (126.9789, 37.5663)]


def test_report_near_the_route_is_placed_on_the_route() -> None:
    shown = reports_on_route([line_report(126.9784, 37.56632)], LINE, 5.0)

    assert [report.position for report in shown] == [(126.9784, 37.5663)]


def test_report_beyond_the_route_end_is_dropped() -> None:
    shown = reports_on_route([line_report(126.9769, 37.5663)], LINE, 5.0)

    assert shown == []


def test_report_beside_the_route_farther_than_limit_is_dropped() -> None:
    # 위도 0.0001 도는 약 11m
    shown = reports_on_route([line_report(126.9784, 37.5664)], LINE, 5.0)

    assert shown == []


def test_route_without_a_line_has_no_reports() -> None:
    assert reports_on_route([line_report(126.9779, 37.5663)], [LINE[0]], 5.0) == []


def test_route_keeps_non_blocking_construction(
    client: TestClient, db_session: Session, sample_graph: Graph
) -> None:
    on_route = sorted(route_edge_ids(client, sample_graph))[0]
    report = add_report(db_session, on_route, kind="construction", blocked=False)

    found = list_reviewable_reports(db_session, frozenset({on_route}), utc_now())

    assert [item.id for item in found] == [report.id]


def test_route_without_reports_has_empty_list(
    client: TestClient, sample_graph: Graph
) -> None:
    response = client.post("/api/route", json=route_request(sample_graph))

    assert response.status_code == 200
    assert response.json()["reports"] == []


def test_no_edges_means_no_query(db_session: Session) -> None:
    add_report(db_session)

    assert list_reviewable_reports(db_session, frozenset(), utc_now()) == []


def post_review(client: TestClient, report_id: int, **body: object) -> object:
    return client.post(f"/api/reports/{report_id}/review", json=body)


def test_review_is_saved(client: TestClient, db_session: Session) -> None:
    report = add_report(db_session)

    response = post_review(
        client, report.id, outcome="improved", comment=" 좋아졌어요 "
    )

    assert response.status_code == 200
    body = response.json()
    assert body["report_id"] == report.id
    assert body["outcome"] == "improved"
    assert body["comment"] == "좋아졌어요"
    assert db_session.scalar(select(func.count()).select_from(ReportReview)) == 1


def test_comment_is_optional(client: TestClient, db_session: Session) -> None:
    report = add_report(db_session)

    response = post_review(client, report.id, outcome="same")

    assert response.status_code == 200
    assert response.json()["comment"] == ""


def test_review_again_replaces_the_old_one(
    client: TestClient, db_session: Session
) -> None:
    report = add_report(db_session)
    first = post_review(client, report.id, outcome="same", comment="그대로")

    second = post_review(client, report.id, outcome="gone")

    assert second.json()["id"] == first.json()["id"]
    reviews = db_session.scalars(select(ReportReview)).all()
    assert [(review.outcome, review.comment) for review in reviews] == [("gone", "")]


def test_each_user_has_own_review(client: TestClient, db_session: Session) -> None:
    report = add_report(db_session)
    post_review(client, report.id, outcome="same")

    other = TestClient(app)
    response = post_review(other, report.id, outcome="gone")

    assert response.status_code == 200
    assert db_session.scalar(select(func.count()).select_from(ReportReview)) == 2


def test_unknown_report_is_404(client: TestClient) -> None:
    response = post_review(client, 999, outcome="same")

    assert response.status_code == 404
    assert response.json()["detail"]["reason"] == "report_not_found"


@pytest.mark.parametrize(
    "fields",
    [
        {"status": "pending"},
        {"status": "rejected"},
        {"status": "resolved"},
        {"kind": "construction", "blocked": True},
        {"expires_at": utc_now() - timedelta(days=1)},
    ],
)
def test_report_not_in_use_is_409(
    client: TestClient, db_session: Session, fields: dict
) -> None:
    report = add_report(db_session, **fields)

    response = post_review(client, report.id, outcome="same")

    assert response.status_code == 409
    assert response.json()["detail"]["reason"] == "report_not_reviewable"


def test_unknown_outcome_is_422(client: TestClient, db_session: Session) -> None:
    report = add_report(db_session)

    assert post_review(client, report.id, outcome="great").status_code == 422


def test_too_long_comment_is_422(client: TestClient, db_session: Session) -> None:
    report = add_report(db_session)

    response = post_review(client, report.id, outcome="same", comment="가" * 201)

    assert response.status_code == 422
