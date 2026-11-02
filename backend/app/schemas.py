from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field

from app.models import ADDRESS_MAX_LENGTH, NAME_MAX_LENGTH, QUERY_MAX_LENGTH
from core.profiles import DEFAULT_PRESET, PRESETS

Longitude = Annotated[float, Field(ge=-180, le=180)]
Latitude = Annotated[float, Field(ge=-90, le=90)]
Coordinate = tuple[Longitude, Latitude]


def known_preset(value: str) -> str:
    if value not in PRESETS:
        raise ValueError(f"알 수 없는 프리셋입니다. 가능한 값: {', '.join(PRESETS)}")
    return value


PresetName = Annotated[
    str, AfterValidator(known_preset), Field(description=", ".join(PRESETS))
]


class RouteRequest(BaseModel):
    start: Coordinate = Field(description="출발지 [경도, 위도]")
    goal: Coordinate = Field(description="도착지 [경도, 위도]")
    # 로그인 연동 전까지 요청으로 이동 조건 프리셋을 받는다.
    preset: PresetName = DEFAULT_PRESET


class TurnPoint(BaseModel):
    index: int = Field(description="꺾는 갈림길이 coordinates 에서 몇 번째인지")
    angle: float = Field(
        description="들어온 방향에서 나가는 방향으로 꺾는 각도(도). 오른쪽이 +"
    )


class RouteResponse(BaseModel):
    distance_m: float
    max_grade: float = Field(description="계단을 뺀 구간 중 가장 가파른 |경사| (비율)")
    ascent_m: float = Field(description="오르막 고도 합")
    steps_count: int
    coordinates: list[Coordinate] = Field(description="경로 지점 [경도, 위도]")
    elevations: list[float]
    distances_m: list[float] = Field(description="출발점부터 각 지점까지 누적 거리")
    turns: list[TurnPoint] = Field(
        description="갈림길에서 다른 길로 꺾어 들어가는 곳. 출발점에서 가까운 순서"
    )
    start_gap_m: float = Field(description="요청한 출발 좌표에서 경로 시작점까지 거리")
    goal_gap_m: float = Field(description="요청한 도착 좌표에서 경로 끝점까지 거리")


class RouteError(BaseModel):
    reason: str
    message: str


class PlaceResponse(BaseModel):
    name: str
    address: str = Field(description="지번 주소")
    road_address: str = Field(description="도로명 주소. 없으면 빈 문자열")
    category: str = Field(description="카카오 카테고리 그룹 이름. 없으면 빈 문자열")
    position: Coordinate = Field(description="[경도, 위도]")
    distance_m: float | None = Field(
        description="기준 좌표에서 거리. 기준 좌표 없이 검색하면 null"
    )


class PlaceSearchResponse(BaseModel):
    places: list[PlaceResponse]


class AddressResponse(BaseModel):
    name: str = Field(
        description="화면에 보일 이름: 건물 이름 → 20m 안 장소(가게 포함) "
        "→ 30m 안 랜드마크 → 'OO 부근'(60m 안 랜드마크) → 동 + 지번"
    )
    building_name: str = Field(description="건물 이름. 없으면 빈 문자열")
    road_address: str = Field(description="도로명 주소. 없으면 빈 문자열")
    address: str = Field(description="지번 주소")


class AddressLookupResponse(BaseModel):
    address: AddressResponse | None = Field(description="주소가 없는 좌표면 null")


class SensorCongestionResponse(BaseModel):
    code: int = Field(description="센서 코드")
    position: Coordinate = Field(description="센서 위치 [경도, 위도]")
    address: str = Field(description="센서 설치 주소")
    visitor_count: int = Field(description="유동인구 원시값(10분 단위 측정)")
    measured_at: datetime = Field(description="측정 시각(한국 시간)")


class CongestionResponse(BaseModel):
    sensors: list[SensorCongestionResponse]


class SessionResponse(BaseModel):
    is_guest: bool = Field(description="카카오·구글 계정이 연결되지 않았으면 true")
    providers: list[str] = Field(description="연결된 계정. kakao, google")
    preset: str = Field(description="저장한 이동 조건 프리셋. 없으면 기본값")


class PresetRequest(BaseModel):
    preset: PresetName


class SearchHistoryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=QUERY_MAX_LENGTH)
    place_name: str | None = Field(
        default=None,
        max_length=NAME_MAX_LENGTH,
        description="검색 결과에서 고른 장소 이름. 고르지 않았으면 null",
    )
    address: str | None = Field(default=None, max_length=ADDRESS_MAX_LENGTH)
    position: Coordinate | None = Field(
        default=None, description="고른 장소 [경도, 위도]"
    )


class SearchHistoryResponse(SearchHistoryRequest):
    id: int
    created_at: datetime


class SearchHistoryListResponse(BaseModel):
    searches: list[SearchHistoryResponse] = Field(description="최근 것부터")


class RouteHistoryRequest(BaseModel):
    start_name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    start: Coordinate = Field(description="출발지 [경도, 위도]")
    goal_name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    goal: Coordinate = Field(description="도착지 [경도, 위도]")
    preset: PresetName
    distance_m: float = Field(ge=0)


class RouteHistoryResponse(RouteHistoryRequest):
    id: int
    created_at: datetime


class RouteHistoryListResponse(BaseModel):
    routes: list[RouteHistoryResponse] = Field(description="최근 것부터")
