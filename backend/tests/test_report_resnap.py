from datetime import timedelta

from sqlalchemy.orm import Session

from app.models import Report, utc_now
from app.services.report_service import resnap_reports
from core.graph import Graph
from core.road_point import nearby_road_points

RADIUS_M = 30.0
ON_ROAD = (126.9779, 37.5663)
FAR_AWAY = (127.5, 37.0)


def add_report(session: Session, lon: float, lat: float, edge_id: int) -> Report:
    now = utc_now()
    report = Report(
        kind="curb",
        blocked=False,
        status="approved",
        photo_name="a.jpg",
        lon=lon,
        lat=lat,
        edge_id=edge_id,
        created_at=now,
        expires_at=now + timedelta(days=90),
    )
    session.add(report)
    session.flush()
    return report


def test_resnap_moves_stale_edge_ids_to_nearest_road(
    db_session: Session, sample_graph: Graph
) -> None:
    nearest = nearby_road_points(sample_graph, *ON_ROAD, RADIUS_M)[0].edge.edge_id
    stale = add_report(db_session, *ON_ROAD, nearest + 1)
    fresh = add_report(db_session, *ON_ROAD, nearest)

    result = resnap_reports(db_session, sample_graph, RADIUS_M)

    assert (result.moved, result.kept, result.off_network) == (1, 1, [])
    assert stale.edge_id == nearest
    assert fresh.edge_id == nearest


def test_resnap_keeps_reports_without_nearby_road(
    db_session: Session, sample_graph: Graph
) -> None:
    report = add_report(db_session, *FAR_AWAY, 7)

    result = resnap_reports(db_session, sample_graph, RADIUS_M)

    assert result.off_network == [report.id]
    assert report.edge_id == 7
