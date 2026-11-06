"""위경도를 기상청 동네예보 5km 격자(nx, ny)로 바꾼다.

기상청이 공개한 Lambert Conformal Conic 투영 공식이다.
"""

import math

EARTH_RADIUS_KM = 6371.00877
GRID_KM = 5.0
# 투영 기준: 표준 위도 2개, 기준점 경위도, 기준점이 놓인 격자 위치
STANDARD_LAT_1 = 30.0
STANDARD_LAT_2 = 60.0
ORIGIN_LON = 126.0
ORIGIN_LAT = 38.0
ORIGIN_X = 43
ORIGIN_Y = 136
# 동네예보가 다루는 격자 범위. 밖이면 예보 자료가 없다.
MAX_X = 149
MAX_Y = 253

_QUARTER_PI = math.pi / 4


def to_grid(lat: float, lon: float) -> tuple[int, int]:
    """(nx, ny). 격자 범위 밖이면 ValueError."""
    radius = EARTH_RADIUS_KM / GRID_KM
    lat1, lat2 = math.radians(STANDARD_LAT_1), math.radians(STANDARD_LAT_2)
    origin_lon, origin_lat = math.radians(ORIGIN_LON), math.radians(ORIGIN_LAT)

    cone = math.log(math.cos(lat1) / math.cos(lat2)) / math.log(
        math.tan(_QUARTER_PI + lat2 / 2) / math.tan(_QUARTER_PI + lat1 / 2)
    )
    scale = math.tan(_QUARTER_PI + lat1 / 2) ** cone * math.cos(lat1) / cone
    origin_r = radius * scale / math.tan(_QUARTER_PI + origin_lat / 2) ** cone

    r = radius * scale / math.tan(_QUARTER_PI + math.radians(lat) / 2) ** cone
    theta = math.radians(lon) - origin_lon
    # 경도 차이를 -180°~180° 로 맞춘다.
    theta = (theta + math.pi) % (2 * math.pi) - math.pi
    theta *= cone

    x = math.floor(r * math.sin(theta) + ORIGIN_X + 0.5)
    y = math.floor(origin_r - r * math.cos(theta) + ORIGIN_Y + 0.5)
    if not (1 <= x <= MAX_X and 1 <= y <= MAX_Y):
        raise ValueError(f"동네예보 격자 범위 밖입니다: ({lat}, {lon})")
    return x, y
