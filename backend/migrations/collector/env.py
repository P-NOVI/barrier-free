"""수집 DB(COLLECTOR_DATABASE_URL) 마이그레이션. alembic.ini 의 [collector]."""

from alembic.util import CommandError
from sqlalchemy import Engine

from app.collector.models import CollectorBase
from app.collector.store import collector_engine
from app.config import get_settings
from app.migrate import run_migrations


def engine() -> Engine:
    settings = get_settings()
    database_url = settings.collector_database_url.get_secret_value()
    if not database_url:
        raise CommandError("COLLECTOR_DATABASE_URL 이 비어 있습니다.")
    return collector_engine(database_url, settings.collector_connect_timeout_s)


run_migrations(CollectorBase.metadata, engine)
