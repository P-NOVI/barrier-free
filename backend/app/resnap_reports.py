"""그래프를 다시 만든 뒤 제보의 길 번호(edge_id)를 제보 좌표로 다시 맞춘다.

backend/ 에서 uv run python -m app.resnap_reports
길 번호는 graph.json.gz 를 내보낸 순서라 그래프를 다시 만들면 바뀐다. 새 그래프를
받은 뒤 한 번 실행한다. 접속 주소는 .env 의 DATABASE_URL 에서 읽는다.
"""

import sys

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_engine
from app.repositories.road_repository import load_graph
from app.services.report_service import resnap_reports


def main() -> int:
    settings = get_settings()
    database_url = settings.database_url.get_secret_value()
    if not database_url:
        print("DATABASE_URL 이 없습니다.")
        return 1
    graph = load_graph(settings.graph_path)
    engine = get_engine(database_url, settings.database_connect_timeout_s)
    try:
        with Session(engine) as session:
            result = resnap_reports(session, graph, settings.report_snap_radius_m)
            session.commit()
    except SQLAlchemyError as error:
        # 예외 문구에 접속 주소가 섞일 수 있어 종류만 남긴다.
        print(f"길 번호를 맞추지 못했습니다 ({type(error).__name__})")
        return 1
    print(f"길 번호가 바뀐 제보 {result.moved}개, 그대로인 제보 {result.kept}개")
    if result.off_network:
        print(f"반경 안에 길이 없어 그대로 둔 제보 id: {result.off_network}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
