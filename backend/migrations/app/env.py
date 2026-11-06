"""앱 DB(DATABASE_URL) 마이그레이션. alembic.ini 의 [alembic]."""

from alembic.util import CommandError
from sqlalchemy import Engine

import app.models  # noqa: F401  모델을 불러와야 Base.metadata 에 테이블이 등록된다.
from app.config import get_settings
from app.db import Base, get_engine
from app.migrate import run_migrations


def engine() -> Engine:
    settings = get_settings()
    database_url = settings.database_url.get_secret_value()
    if not database_url:
        raise CommandError("backend/.env 의 DATABASE_URL 이 비어 있습니다.")
    return get_engine(database_url, settings.database_connect_timeout_s)


run_migrations(Base.metadata, engine)
