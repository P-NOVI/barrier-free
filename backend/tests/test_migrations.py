import sys

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import MetaData, create_engine, inspect
from sqlalchemy.pool import StaticPool

from app.collector import __main__ as collector
from app.collector import import_sqlite
from app.collector.models import CollectorBase
from app.config import get_settings
from app.db import Base
from app.migrate import APP_DB, COLLECTOR_DB, alembic_config, is_up_to_date

DATABASES = [(APP_DB, Base.metadata), (COLLECTOR_DB, CollectorBase.metadata)]


def memory_engine():
    return create_engine("sqlite://", poolclass=StaticPool)


@pytest.mark.parametrize(("name", "metadata"), DATABASES)
def test_migrations_match_models(migrate, name: str, metadata: MetaData) -> None:
    """모델을 바꾸고 마이그레이션을 빠뜨리면 실패한다.

    backend/ 에서 uv run alembic [-n collector] revision --autogenerate 로 만든다.
    """
    engine = memory_engine()

    migrate(engine, name)

    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), metadata) == []


@pytest.mark.parametrize(("name", "metadata"), DATABASES)
def test_downgrade_removes_tables(migrate, name: str, metadata: MetaData) -> None:
    engine = memory_engine()
    migrate(engine, name)
    config = alembic_config(name)

    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "base")

    assert inspect(engine).get_table_names() == ["alembic_version"]


@pytest.mark.parametrize("name", [APP_DB, COLLECTOR_DB])
def test_is_up_to_date_after_upgrade(migrate, name: str) -> None:
    engine = memory_engine()
    assert not is_up_to_date(engine, name)

    migrate(engine, name)

    assert is_up_to_date(engine, name)


def test_collector_stops_when_not_migrated(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("COLLECTOR_DATABASE_URL", f"sqlite:///{tmp_path / 'c.db'}")
    # main() 은 명령줄 인자로 작업을 고른다. pytest 인자가 섞이지 않게 비운다.
    monkeypatch.setattr(sys, "argv", ["collector"])
    get_settings.cache_clear()

    assert collector.main() == 1
    assert "alembic -n collector upgrade head" in capsys.readouterr().out


def test_import_sqlite_stops_when_not_migrated(tmp_path, monkeypatch, capsys) -> None:
    source = tmp_path / "local.db"
    source.touch()
    monkeypatch.setenv("COLLECTOR_DATABASE_URL", f"sqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setattr(sys, "argv", ["import_sqlite", str(source)])
    get_settings.cache_clear()

    assert import_sqlite.main() == 1
    assert "alembic -n collector upgrade head" in capsys.readouterr().out
