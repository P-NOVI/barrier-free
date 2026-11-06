from datetime import datetime
from typing import Any

from sqlalchemy import Engine, make_url
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from app.db import get_engine
from app.services.weather_service import KST

# 수집 DB에 마지막 마이그레이션이 적용되지 않았을 때 알려 주는 말
STALE_SCHEMA = (
    "수집 DB 테이블이 최신이 아닙니다. "
    "backend/ 에서 `uv run alembic -n collector upgrade head` 를 실행하세요."
)

# 한 INSERT 에 넣는 행 수. PostgreSQL 바인드 변수 한도(65535)보다 넉넉히 작게 둔다.
INSERT_CHUNK = 1000


def collector_engine(database_url: str, connect_timeout_s: int) -> Engine:
    """수집 DB 엔진. 드라이버가 없는 postgresql:// 주소는 psycopg 로 맞춘다."""
    url = make_url(database_url)
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    return get_engine(url.render_as_string(hide_password=False), connect_timeout_s)


def insert_new(session: Session, model: type, rows: list[dict[str, Any]]) -> int:
    """키가 같은 행이 이미 있으면 건너뛰고 넣는다. 새로 넣은 행 수."""
    dialect = session.get_bind().dialect.name
    insert = postgresql.insert if dialect == "postgresql" else sqlite.insert
    keys = model.__table__.primary_key.columns
    count = 0
    for start in range(0, len(rows), INSERT_CHUNK):
        # psycopg 는 이 INSERT 의 rowcount 를 -1 로 주므로, 넣은 행의 키를 받아 센다.
        statement = (
            insert(model)
            .values(rows[start : start + INSERT_CHUNK])
            .on_conflict_do_nothing()
            .returning(*keys)
        )
        count += len(session.execute(statement).all())
    return count


def as_kst(moment: datetime) -> datetime:
    """DB에서 읽은 시각을 한국 시간으로.

    SQLite(테스트)는 넣은 한국 시각을 시간대 없이 돌려준다.
    """
    if moment.tzinfo is None:
        return moment.replace(tzinfo=KST)
    return moment.astimezone(KST)
