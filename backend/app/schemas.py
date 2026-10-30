from typing import Annotated

from pydantic import BaseModel, Field, field_validator

from core.profiles import DEFAULT_PRESET, PRESETS

Longitude = Annotated[float, Field(ge=-180, le=180)]
Latitude = Annotated[float, Field(ge=-90, le=90)]
Coordinate = tuple[Longitude, Latitude]


class RouteRequest(BaseModel):
    start: Coordinate = Field(description="출발지 [경도, 위도]")
    goal: Coordinate = Field(description="도착지 [경도, 위도]")
    # 로그인 연동 전까지 요청으로 이동 조건 프리셋을 받는다.
    preset: str = Field(default=DEFAULT_PRESET, description=", ".join(PRESETS))

    @field_validator("preset")
    @classmethod
    def known_preset(cls, value: str) -> str:
        if value not in PRESETS:
            raise ValueError(
                f"알 수 없는 프리셋입니다. 가능한 값: {', '.join(PRESETS)}"
            )
        return value


class RouteResponse(BaseModel):
    distance_m: float
    max_grade: float = Field(description="계단을 뺀 구간 중 가장 가파른 |경사| (비율)")
    ascent_m: float = Field(description="오르막 고도 합")
    steps_count: int
    coordinates: list[Coordinate] = Field(description="경로 지점 [경도, 위도]")
    elevations: list[float]
    distances_m: list[float] = Field(description="출발점부터 각 지점까지 누적 거리")
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
