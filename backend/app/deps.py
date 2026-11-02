from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.config import Settings, get_settings
from app.repositories.road_repository import load_graph
from core.graph import Graph

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_graph(settings: SettingsDep) -> Graph:
    try:
        return load_graph(settings.graph_path)
    except FileNotFoundError as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "reason": "graph_unavailable",
                "message": "경로 데이터가 없습니다. pipeline 04 단계를 확인하세요.",
            },
        ) from error


GraphDep = Annotated[Graph, Depends(get_graph)]
