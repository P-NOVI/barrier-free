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
    # pipeline/steps/05_export_sdot_sensors.py 가 만드는 파일
    sensors_path: Path = REPO_ROOT / "data" / "processed" / "sdot_sensors.json"
    # 서울 열린데이터광장 S-DoT 유동인구(실시간) API. 키는 backend/.env 에만 둔다.
    # 키가 요청 주소에 들어가므로 주소를 로그나 응답에 내보내지 않는다.
    sdot_api_key: SecretStr = SecretStr("")
    sdot_base_url: str = "http://openapi.seoul.go.kr:8088"
    sdot_timeout_s: float = 5.0
    # 한 번에 받는 행 수. 서울 열린데이터광장이 한 번에 주는 최대 개수(1000)다.
    # 목록은 최신순이라 센서 134개의 최근 측정값을 담기에 충분하다.
    sdot_page_size: int = 1000
    # 센서는 10분마다 측정한다. 이 시간 안에는 API를 다시 부르지 않는다.
    sdot_cache_ttl_s: float = 60.0
    # PostgreSQL 접속 주소. 비밀번호가 들어 있으므로 backend/.env 에만 둔다.
    # 형식: postgresql+psycopg://barrierfree:<비밀번호>@localhost:5432/barrierfree
    database_url: SecretStr = SecretStr("")
    # DB가 꺼져 있을 때 이 시간만 기다리고 실패한다.
    database_connect_timeout_s: int = 3
    # 지도에서 누른 곳의 이름
    # - place_on_spot 안 장소는 분류와 상관없이(가게도) 그 이름으로 부른다.
    #   가장 가까운 곳과 same_spot 안(같은 건물쯤)이면 지도에 이름이 보이는 곳을 쓴다.
    # - 없으면 landmark_radius 안 랜드마크. landmark_on_spot 보다 멀면 'OO 부근'
    place_on_spot_m: int = 20
    same_spot_m: float = 5.0
    landmark_radius_m: int = 60
    landmark_on_spot_m: float = 30.0


@cache
def get_settings() -> Settings:
    return Settings()
