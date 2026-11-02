from functools import cache

from sqlalchemy import Engine, create_engine, make_url
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """모든 테이블 모델의 부모 클래스."""


@cache
def get_engine(database_url: str, connect_timeout_s: int) -> Engine:
    # psycopg 는 기본으로 접속을 끝없이 기다리므로 PostgreSQL 이면 시간을 정한다.
    connect_args = (
        {"connect_timeout": connect_timeout_s}
        if make_url(database_url).get_backend_name() == "postgresql"
        else {}
    )
    # DB를 껐다 켜면 풀에 남은 연결이 끊겨 있으므로 쓰기 전에 확인한다.
    return create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)


def create_tables(engine: Engine) -> None:
    """없는 테이블만 만든다. 이미 있는 테이블의 칸은 바꾸지 않는다."""
    # 모델을 불러와야 Base.metadata 에 테이블이 등록된다.
    import app.models  # noqa: F401

    Base.metadata.create_all(engine)
