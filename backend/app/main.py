from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.repositories.road_repository import load_graph
from app.routers import places, routes


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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
