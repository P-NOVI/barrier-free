from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.config import get_settings
from app.deps import DbSessionDep
from app.repositories.road_repository import load_graph
from app.routers import congestion, places, routes


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # 첫 경로 요청이 느리지 않도록 서버 시작 때 그래프를 한 번 읽어 둔다.
    graph_path = get_settings().graph_path
    if graph_path.exists():
        load_graph(graph_path)
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(routes.router, prefix="/api")
app.include_router(places.router, prefix="/api")
app.include_router(congestion.router, prefix="/api")


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
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "reason": "db_unavailable",
                "message": "DB에 접속할 수 없습니다. "
                "docker compose 로 DB가 켜져 있는지 확인하세요.",
            },
        ) from error
    return {"status": "ok"}
