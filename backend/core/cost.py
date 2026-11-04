import math

from core.graph import Arc, Trail
from core.profiles import CONGESTION_WEIGHTS, Profile
from core.slope import GradeLevel, grade_level

# 경사 한계 이하 구간의 배율. 초안 값이다.
SLOPE_FACTORS: dict[GradeLevel, float] = {
    GradeLevel.EASY: 1.0,
    GradeLevel.MODERATE: 1.5,
    GradeLevel.HARD: 3.0,
}
# 1/12 보다 가파른 구간을 더 나눈 배율 (이 경사 초과, 배율). 가파른 것부터 본다.
# 일반 보행은 경사 상한이 없어서, 이게 없으면 30% 산길도 9% 오르막과 비용이 같다.
# 초안 값이다.
STEEP_FACTORS: tuple[tuple[float, float], ...] = ((0.25, 10.0), (0.15, 5.0))
# 등산로 배율. 경사·계단 배율에 곱한다. 초안 값이다.
TRAIL_FACTORS: dict[Trail, float] = {Trail.HIKING: 2.0, Trail.MOUNTAIN: 10.0}
# 인도가 따로 있는 중심선(차도) 배율. 옆 인도로 가게 한다. 지우지 않는 것은 인도가
# 한쪽만 있거나 끊긴 곳에서 길이 막히지 않게 하려는 것이다. 초안 값이다.
SIDEWALK_SEPARATE_FACTOR = 3.0


def is_passable(arc: Arc, profile: Profile) -> bool:
    """지나갈 수 있는 구간인지 판정한다.

    계단은 경사 부호로 상행·하행을 정하고(0 은 상행),
    경사 한계 대신 계단 가능 여부로 본다.
    """
    if not arc.walk_ok:
        return False
    if profile.needs_wheelchair_access and not arc.wheelchair_ok:
        return False
    if arc.steps:
        return profile.stairs_up if arc.grade >= 0 else profile.stairs_down
    return profile.max_grade is None or abs(arc.grade) <= profile.max_grade


def slope_factor(grade: float) -> float:
    steepness = abs(grade)
    for min_grade, factor in STEEP_FACTORS:
        if steepness > min_grade:
            return factor
    return SLOPE_FACTORS[grade_level(grade)]


def arc_cost(arc: Arc, profile: Profile, congestion: float = 0.0) -> float:
    """구간 비용 = 길이 × 경사·계단 배율 × 등산로 배율 × 차도 배율 × 혼잡 배율.

    계단은 계단 배율과 그 경사의 배율 중 큰 값을 쓴다. 계단 배율이 1 인 일반 보행이
    산 계단으로 능선을 넘지 않게 한다. 지나갈 수 없으면 inf.
    """
    if not is_passable(arc, profile):
        return math.inf
    factor = slope_factor(arc.grade)
    if arc.steps:
        factor = max(factor, profile.stair_factor)
    trail_factor = TRAIL_FACTORS[arc.trail] if arc.trail else 1.0
    road_factor = SIDEWALK_SEPARATE_FACTOR if arc.sidewalk_separate else 1.0
    congestion_factor = (
        1 + CONGESTION_WEIGHTS[profile.congestion_tolerance] * congestion
    )
    return arc.length * factor * trail_factor * road_factor * congestion_factor
