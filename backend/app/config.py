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
    # pipeline/steps/07_export_entrances.py 가 만드는 파일. 없으면 출입구 없이 찾는다.
    entrances_path: Path = REPO_ROOT / "data" / "processed" / "entrances.json.gz"
    # pipeline/steps/08_export_sites.py 가 만드는 파일. 없으면 담장을 보지 않고 찾는다.
    sites_path: Path = REPO_ROOT / "data" / "processed" / "sites.json.gz"
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
    # 기상청 API허브 동네예보(초단기실황·초단기예보·단기예보).
    # 키는 backend/.env 에만 둔다. 키가 요청 주소의 쿼리에 들어가므로
    # 주소를 로그나 응답에 내보내지 않는다.
    kma_api_key: SecretStr = SecretStr("")
    kma_base_url: str = (
        "https://apihub.kma.go.kr/api/typ02/openApi/VilageFcstInfoService_2.0"
    )
    kma_timeout_s: float = 5.0
    # 한 번에 받는 행 수. 단기예보는 1,000건이 넘어서 쪽을 나눠 받는다.
    kma_page_size: int = 1000
    # 기상청 자료는 한 시간 또는 세 시간마다 갱신된다.
    # 이 시간 안에는 같은 격자·기준 시각을 다시 부르지 않는다.
    kma_cache_ttl_s: float = 600.0
    # 경로 탐색의 길별 혼잡도(core/congestion.py). 10분 유동인구가 이 값 이상이면 1.
    # 초안 값이다. 2026-11-03 10~15시 S-DoT 3,000행의 95% 지점(296명)에 맞췄다.
    congestion_full_count: float = 300.0
    # 센서에서 이 거리 안을 지나는 길에 그 센서의 혼잡도를 붙인다. 초안 값이다.
    congestion_radius_m: float = 50.0
    # 경로의 '붐비는 길' 길이(busy_m)는 혼잡도가 이 값 이상인 길만 더한다.
    # 0.5 는 10분 유동인구 150명이다.
    congestion_busy_level: float = 0.5
    # 예측 유동인구(명/시간)를 10분 유동인구로 바꿀 때 나누는 값(한 시간의 10분
    # 구간 수). 그래서 예측도 congestion_full_count 와 같은 기준으로 혼잡도가 된다.
    forecast_bins_per_hour: int = 6
    # 출발 시각은 오늘부터 이 날 수 안(모레까지)에서만 고른다. 매일 예측 배치
    # (ml foot_traffic.daily)가 오늘·내일·모레를 예측한다.
    route_forecast_days: int = 3
    # 시각별 예측 혼잡도를 이 시간 동안 들고 있는다. 예측은 하루 한 번 바뀐다.
    forecast_cache_ttl_s: float = 600.0
    # 경로 탐색에서 뺄 길(승인된 통행 불가 제보)을 이 시간 안에는 다시 읽지 않는다.
    # 승인·만료가 경로에 반영되기까지 최대 이만큼 늦다.
    closed_road_cache_ttl_s: float = 60.0
    # PostgreSQL 접속 주소. 비밀번호가 들어 있으므로 backend/.env 에만 둔다.
    # 형식: postgresql+psycopg://barrierfree:<비밀번호>@localhost:5432/barrierfree
    database_url: SecretStr = SecretStr("")
    # DB가 꺼져 있을 때 이 시간만 기다리고 실패한다.
    database_connect_timeout_s: int = 3
    # 유동인구·날씨 수집 DB(Supabase) 접속 주소. 앱 DB(DATABASE_URL)와 따로 둔다.
    # Supabase 의 postgresql://... 주소를 그대로 넣어도 된다(드라이버는 psycopg).
    collector_database_url: SecretStr = SecretStr("")
    # 외부 DB라 로컬 앱 DB보다 길게 기다린다.
    collector_connect_timeout_s: int = 10
    # S-DoT 는 DB의 최신 측정 시각에서 이만큼 앞까지 최신 쪽부터 거슬러 받는다.
    # 늦게 올라온 행도 받으려고 겹쳐 받는다(이미 있는 행은 건너뛴다).
    collector_sdot_overlap_minutes: int = 60
    # 한 번에 받는 최대 쪽 수. 1000행이 약 1.5시간치라 하루가 약 12쪽, 300쪽은 약 25일.
    # 여기에 걸리면 넣지 않고 실패로 끝나 다음 실행이 같은 지점부터 다시 받는다.
    collector_sdot_max_pages: int = 300
    # 수집 DB가 비었을 때만 받는 S-DoT 최신 행 수.
    collector_sdot_rows: int = 2000
    # 실황은 지난 이 시간 안에서 DB에 없는 정시만 받는다. 기상청은 24시간 안만 준다.
    collector_backfill_hours: int = 12
    # 하루치 예보: 이 시(KST) 단기예보 발표분을 받아 발표 뒤 이 시간만큼 저장한다.
    # 67시간은 05시 발표부터 모레 24시까지다. 유동인구 예측(ml foot_traffic.daily)이
    # 오늘·내일·모레 날씨로 쓴다.
    collector_daily_issue_hour: int = 5
    collector_daily_hours: int = 67
    # 자치구 날씨 위치(센서 위치 평균)는 지난 이 기간에 모은 센서·자치구 짝으로 구한다.
    # 유동인구는 하루 한 번 받으므로, 그 실행이 며칠 빠져도 날씨가 멈추지 않게
    # 넉넉히 둔다.
    collector_district_days: int = 7
    # 마지막 접속 후 이 기간이 지난 게스트는 이력과 함께 지운다.
    # 경로 이력은 위치 정보이므로 기한 없이 쌓아 두지 않는다.
    guest_retention_days: int = 30
    # 이 기간 동안 쓰지 않은 토큰은 만료된다.
    token_idle_days: int = 30
    # 사용자마다 검색·경로 이력을 최근 이만큼만 남긴다.
    history_keep: int = 50
    # 사용자마다 즐겨찾기·내 장소를 합쳐 이만큼까지 저장한다.
    saved_places_max: int = 100
    # 사용자마다 즐겨찾기한 경로(내 경로)를 이만큼까지 저장한다.
    saved_routes_max: int = 100
    # 게스트·회원 토큰을 담는 쿠키. 자바스크립트로 읽을 수 없게(HttpOnly) 준다.
    auth_cookie_name: str = "bf_token"
    # https 에서만 쿠키를 보낸다. 배포 환경에서는 AUTH_COOKIE_SECURE=true
    auth_cookie_secure: bool = False
    # 카카오·구글 로그인. 키는 backend/.env 에만 둔다.
    # 카카오 client_id 는 kakao_rest_api_key 를 쓴다.
    kakao_client_secret: SecretStr = SecretStr("")
    kakao_auth_base_url: str = "https://kauth.kakao.com"
    kakao_user_url: str = "https://kapi.kakao.com/v2/user/me"
    google_client_id: str = ""
    google_client_secret: SecretStr = SecretStr("")
    google_authorize_url: str = "https://accounts.google.com/o/oauth2/v2/auth"
    google_token_url: str = "https://oauth2.googleapis.com/token"
    google_user_url: str = "https://openidconnect.googleapis.com/v1/userinfo"
    oauth_timeout_s: float = 5.0
    # 카카오·구글 콘솔에 등록한 Redirect URI 의 앞부분.
    # 실제 주소는 {이 값}/api/auth/{kakao|google}/callback
    # 쿠키는 포트를 구분하지 않으므로 화면(localhost:5173)과 호스트 이름만 같으면 된다.
    oauth_redirect_base_url: str = "http://localhost:8000"
    # 로그인을 마치고 돌아갈 화면 주소
    frontend_url: str = "http://localhost:5173"
    # 로그인 위조를 막는 state 값을 담는 쿠키. 로그인을 마칠 때까지만 둔다.
    oauth_state_cookie_name: str = "bf_oauth_state"
    oauth_state_ttl_s: int = 600
    # 지도에서 누른 곳의 이름
    # - place_on_spot 안 장소는 분류와 상관없이(가게도) 그 이름으로 부른다.
    #   가장 가까운 곳과 same_spot 안(같은 건물쯤)이면 지도에 이름이 보이는 곳을 쓴다.
    # - 없으면 landmark_radius 안 랜드마크. landmark_on_spot 보다 멀면 'OO 부근'
    place_on_spot_m: int = 20
    same_spot_m: float = 5.0
    landmark_radius_m: int = 60
    landmark_on_spot_m: float = 30.0
    # 길 위 문제 제보 사진을 저장하는 폴더. 사진에 사람 얼굴·번호판이 있을 수 있어
    # 저장소에 커밋하지 않고(.gitignore) 관리자에게만 보여 준다.
    # Supabase Storage 키가 없을 때만 쓴다(로컬 개발).
    report_photo_dir: Path = REPO_ROOT / "data" / "report_photos"
    report_photo_max_bytes: int = 5 * 1024 * 1024
    # 제보 사진을 올리는 Supabase Storage 비공개 버킷. 키는 backend/.env 에만 둔다.
    # supabase_url 과 supabase_service_key 가 모두 있으면 사진을 여기에 저장한다.
    supabase_url: str = ""
    supabase_service_key: SecretStr = SecretStr("")
    supabase_photo_bucket: str = "report-photos"
    supabase_timeout_s: float = 10.0
    # 제보 좌표가 도로망에서 이보다 멀면 제보를 받지 않는다. 초안 값이다.
    report_snap_radius_m: float = 30.0
    # 만료된 제보를 이 기간이 지나면 사진과 함께 지운다. 서버를 켤 때 정리한다.
    # 사진에 얼굴·번호판이 있을 수 있어 기한 없이 쌓아 두지 않는다.
    report_retention_days: int = 30
    # 관리자 계정. "google:1234,kakao:5678" 처럼 provider:provider_user_id 를
    # 쉼표로 잇는다.
    # 카카오는 이메일이 안 내려올 수 있어 이메일이 아니라 계정 번호로 정한다.
    admin_accounts: str = ""

    @property
    def admin_account_set(self) -> frozenset[tuple[str, str]]:
        pairs = (item.strip().partition(":") for item in self.admin_accounts.split(","))
        return frozenset(
            (provider.strip(), user_id.strip())
            for provider, _, user_id in pairs
            if provider.strip() and user_id.strip()
        )


@cache
def get_settings() -> Settings:
    return Settings()
