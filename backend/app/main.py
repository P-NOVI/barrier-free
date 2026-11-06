import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_engine
from app.deps import DbSessionDep
from app.migrate import APP_DB, is_up_to_date
from app.repositories.report_repository import purge_expired_reports
from app.repositories.road_repository import load_entrances, load_graph, load_sites
from app.repositories.user_repository import purge_inactive_guests
from app.routers import (
    admin,
    auth,
    congestion,
    me,
    places,
    reports,
    routes,
    weather,
)

logger = logging.getLogger(__name__)

DB_UNAVAILABLE = {
    "reason": "db_unavailable",
    "message": "DB에 접속할 수 없습니다. "
    "docker compose 로 DB가 켜져 있는지 확인하세요.",
}


def prepare_database(settings: Settings) -> None:
    """테이블이 최신인지 보고 오래된 게스트·만료된 제보를 지운다.

    DB가 꺼져 있어도 서버는 켠다.
    """
    database_url = settings.database_url.get_secret_value()
    if not database_url:
        return
    engine = get_engine(database_url, settings.database_connect_timeout_s)
    try:
        if not is_up_to_date(engine, APP_DB):
            logger.warning(
                "DB 테이블이 최신이 아닙니다. "
                "backend/ 에서 `uv run alembic upgrade head` 를 실행하세요."
            )
            return
        with Session(engine) as session:
            purge_inactive_guests(session, settings.guest_retention_days)
            photo_names = purge_expired_reports(session, settings.report_retention_days)
            session.commit()
            # DB 에서 지운 뒤에 파일을 지워, 커밋이 실패해도 사진만 사라지지 않게 한다.
            for photo_name in photo_names:
                (settings.report_photo_dir / photo_name).unlink(missing_ok=True)
    except OperationalError:
        # 오류 문구에 접속 정보가 섞일 수 있어 로그에 남기지 않는다.
        logger.warning("DB에 접속할 수 없어 테이블을 준비하지 못했습니다.")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    # 첫 경로 요청이 느리지 않도록 서버 시작 때 그래프를 한 번 읽어 둔다.
    if settings.graph_path.exists():
        load_graph(settings.graph_path)
    load_entrances(settings.entrances_path)
    load_sites(settings.sites_path)
    prepare_database(settings)
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins,
    # 게스트·회원 토큰 쿠키를 주고받는다.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(routes.router, prefix="/api")
app.include_router(places.router, prefix="/api")
app.include_router(congestion.router, prefix="/api")
app.include_router(me.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(weather.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(admin.router, prefix="/api")


@app.exception_handler(OperationalError)
def db_unavailable(_: Request, __: OperationalError) -> JSONResponse:
    # 오류 문구에 접속 정보가 섞일 수 있어 응답에 그대로 내보내지 않는다.
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": DB_UNAVAILABLE},
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/db")
def health_db(session: DbSessionDep) -> dict[str, str]:
    try:
        session.execute(text("select 1"))
    except OperationalError as error:
        # 오류 문구에 접속 정보가 섞일 수 있어 응답에 그대로 내보내지 않는다.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail=DB_UNAVAILABLE
        ) from error
    return {"status": "ok"}
