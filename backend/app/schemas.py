from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, model_validator

from app.models import (
    ADDRESS_MAX_LENGTH,
    LABEL_MAX_LENGTH,
    NAME_MAX_LENGTH,
    QUERY_MAX_LENGTH,
    REVIEW_COMMENT_MAX_LENGTH,
)
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


class RouteReport(BaseModel):
    """경로가 지나는 승인된 제보. 도착 후 리뷰를 받을 장소다."""

    id: int
    kind: str
    description: str | None
    position: Coordinate = Field(description="제보 위치 [경도, 위도]")


class RouteResponse(BaseModel):
    distance_m: float
    duration_s: float = Field(
        description="이동 조건의 평균 속도로 distance_m 을 가는 예상 시간(초)"
    )
    max_grade: float = Field(description="계단을 뺀 구간 중 가장 가파른 |경사| (비율)")
    ascent_m: float = Field(description="오르막 고도 합")
    steps_count: int
    coordinates: list[Coordinate] = Field(description="경로 지점 [경도, 위도]")
    elevations: list[float]
    distances_m: list[float] = Field(description="출발점부터 각 지점까지 누적 거리")
    turns: list[TurnPoint] = Field(
        description="갈림길에서 다른 길로 꺾어 들어가는 곳. 출발점에서 가까운 순서"
    )
    start_gap_m: float = Field(
        description="요청한 출발 좌표(또는 거친 출입구)에서 경로 시작점까지 거리"
    )
    goal_gap_m: float = Field(
        description="요청한 도착 좌표(또는 거친 출입구)에서 경로 끝점까지 거리"
    )
    start_entrance: Coordinate | None = Field(
        default=None, description="출발지가 건물·시설 안이라 거친 출입구 [경도, 위도]"
    )
    goal_entrance: Coordinate | None = Field(
        default=None, description="도착지가 건물·시설 안이라 거친 출입구 [경도, 위도]"
    )
    reports: list[RouteReport] = Field(
        default_factory=list,
        description="경로가 지나는 승인된 제보. 통행 불가 공사는 경로가 피하므로 없다.",
    )


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


class WeatherResponse(BaseModel):
    source: Literal["observation", "ultra_short_forecast", "short_forecast"] = Field(
        description="observation 은 현재 관측, 나머지는 예보"
    )
    time: datetime = Field(description="날씨가 해당하는 정시(한국 시간)")
    temp_c: float = Field(description="기온(℃)")
    rain_mm: float = Field(
        description="그 시간의 강수량(mm). '1mm 미만'은 0.5, 범위는 가운데 값"
    )
    precipitation: Literal["none", "rain", "sleet", "snow", "shower"] = Field(
        description="강수 형태. none 은 비·눈 없음"
    )


class SessionResponse(BaseModel):
    is_guest: bool = Field(description="카카오·구글 계정이 연결되지 않았으면 true")
    providers: list[str] = Field(description="연결된 계정. kakao, google")
    preset: str = Field(description="저장한 이동 조건 프리셋. 없으면 기본값")
    is_admin: bool = Field(default=False, description="관리자 계정이면 true")


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


class SavedRouteRequest(RouteHistoryRequest):
    """즐겨찾기할 경로. 출발·도착 위치와 이동 조건이 같으면 바꿔 저장한다."""


class SavedRouteResponse(SavedRouteRequest):
    id: int
    created_at: datetime


class SavedRouteListResponse(BaseModel):
    routes: list[SavedRouteResponse] = Field(description="최근 것부터")


class SavedPlaceRequest(BaseModel):
    kind: Literal["favorite", "mine"] = Field(
        description="favorite 는 즐겨찾기, mine 은 이름을 붙인 내 장소"
    )
    label: str | None = Field(
        default=None,
        min_length=1,
        max_length=LABEL_MAX_LENGTH,
        description="내 장소 이름(집, 회사 등). 즐겨찾기는 null",
    )
    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    address: str | None = Field(default=None, max_length=ADDRESS_MAX_LENGTH)
    position: Coordinate = Field(description="장소 [경도, 위도]")

    @model_validator(mode="after")
    def label_matches_kind(self) -> "SavedPlaceRequest":
        if (self.kind == "mine") != (self.label is not None):
            raise ValueError("내 장소에만 label 을 붙입니다.")
        return self


class SavedPlaceResponse(SavedPlaceRequest):
    id: int
    created_at: datetime


class SavedPlaceListResponse(BaseModel):
    places: list[SavedPlaceResponse] = Field(description="최근 것부터")


class ReportResponse(BaseModel):
    id: int
    kind: str
    blocked: bool
    status: str
    description: str | None
    lon: float
    lat: float
    created_at: datetime
    expires_at: datetime


class AdminReportResponse(ReportResponse):
    photo_url: str = Field(description="관리자만 열 수 있는 제보 사진 주소")


class AdminReportListResponse(BaseModel):
    reports: list[AdminReportResponse] = Field(description="오래된 것부터")


class ReportListResponse(BaseModel):
    reports: list[ReportResponse] = Field(description="최근 것부터")


class ReviewRequest(BaseModel):
    outcome: Literal["same", "improved", "gone"] = Field(
        description="same 은 그대로, improved 는 나아짐, gone 은 사라짐"
    )
    comment: str = Field(default="", max_length=REVIEW_COMMENT_MAX_LENGTH)


class ReviewResponse(ReviewRequest):
    id: int
    report_id: int
    created_at: datetime


class ReportUpdateRequest(BaseModel):
    """보낸 항목만 바꾼다. 위치와 사진은 고칠 수 없다."""

    kind: str | None = None
    blocked: bool | None = None
    description: str | None = Field(
        default=None, description="빈 문자열이면 설명을 지운다"
    )
