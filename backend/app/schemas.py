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
