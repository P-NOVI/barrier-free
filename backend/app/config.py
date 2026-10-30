from functools import cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """환경변수 또는 backend/.env 로 바꿀 수 있는 설정."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # pipeline/steps/04_export_graph.py 가 만드는 파일
    graph_path: Path = REPO_ROOT / "data" / "processed" / "graph.json.gz"
    # 출발·도착 좌표가 도로망에서 이보다 멀면 경로를 찾지 않는다.
    max_snap_distance_m: float = 200.0
    allowed_origins: list[str] = ["http://localhost:5173"]
    # 카카오 로컬(장소 검색) API. 키는 backend/.env 에만 둔다.
    kakao_rest_api_key: SecretStr = SecretStr("")
    kakao_local_base_url: str = "https://dapi.kakao.com"
    kakao_timeout_s: float = 3.0


@cache
def get_settings() -> Settings:
    return Settings()
