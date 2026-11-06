"""DB 마이그레이션(Alembic) 실행과 확인.

backend/ 에서 실행하고 접속 주소는 .env 에서 읽는다.
- 앱 DB(DATABASE_URL): uv run alembic upgrade head
- 수집 DB(COLLECTOR_DATABASE_URL): uv run alembic -n collector upgrade head
- 모델을 바꾼 뒤: uv run alembic [-n collector] revision --autogenerate -m "설명"
- 수집 워크플로: uv run python -m app.migrate collector
  GitHub Actions 로그는 공개되므로 실패하면 오류 종류만 출력한다.

설정 파일 alembic.ini 에는 한글을 쓰지 않는다.
Alembic 이 OS 기본 인코딩(한국어 Windows 는 cp949)으로 읽어 UTF-8 한글에서 멈춘다.
"""

import sys
from collections.abc import Callable
from logging.config import fileConfig
from pathlib import Path

from alembic import command, context
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.util import CommandError
from sqlalchemy import Connection, Engine, MetaData
from sqlalchemy.exc import SQLAlchemyError

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"
# alembic.ini 의 섹션 이름. alembic 명령의 -n 값과 같다.
APP_DB = "alembic"
COLLECTOR_DB = "collector"


def alembic_config(name: str) -> Config:
    return Config(ALEMBIC_INI, ini_section=name)


def is_up_to_date(engine: Engine, name: str) -> bool:
    """DB에 마지막 마이그레이션까지 적용됐는지."""
    heads = set(ScriptDirectory.from_config(alembic_config(name)).get_heads())
    with engine.connect() as connection:
        current = set(MigrationContext.configure(connection).get_current_heads())
    return current == heads


def run_migrations(metadata: MetaData, engine: Callable[[], Engine]) -> None:
    """migrations/*/env.py 에서 부른다.

    테스트는 config.attributes["connection"] 으로 연결을 넘겨 .env 를 읽지 않는다.
    """
    connection = context.config.attributes.get("connection")
    if connection is not None:
        migrate(connection, metadata)
        return
    if context.config.config_file_name:
        fileConfig(context.config.config_file_name, disable_existing_loggers=False)
    with engine().connect() as connection:
        migrate(connection, metadata)


def migrate(connection: Connection, metadata: MetaData) -> None:
    context.configure(
        connection=connection,
        target_metadata=metadata,
        # 테스트의 SQLite 는 칸 변경(ALTER)을 못 해서, 새로 만드는 마이그레이션이
        # 테이블을 새로 만들어 옮기는 batch 방식으로 쓰이게 한다.
        # PostgreSQL 에서는 그냥 ALTER 로 실행된다.
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def upgrade(name: str) -> int:
    """마지막 마이그레이션까지 적용한다. 실패하면 종료 코드 1."""
    try:
        command.upgrade(alembic_config(name), "head")
    except CommandError as error:
        print(f"마이그레이션 실패: {error}")
        return 1
    except SQLAlchemyError as error:
        # 예외 문구에 접속 주소가 섞일 수 있어 종류만 남긴다.
        print(f"마이그레이션 실패 ({type(error).__name__})")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(upgrade(sys.argv[1] if len(sys.argv) > 1 else APP_DB))
