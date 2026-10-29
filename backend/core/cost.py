import math

from core.graph import Arc
from core.profiles import CONGESTION_WEIGHTS, Profile
from core.slope import GradeLevel, grade_level

# 경사 한계 이하 구간의 배율. 초안 값이다.
SLOPE_FACTORS: dict[GradeLevel, float] = {
    GradeLevel.EASY: 1.0,
    GradeLevel.MODERATE: 1.5,
    GradeLevel.HARD: 3.0,
}


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


def arc_cost(arc: Arc, profile: Profile, congestion: float = 0.0) -> float:
    """구간 비용 = 길이 × (계단 배율 또는 경사 배율) × 혼잡 배율.

    지나갈 수 없으면 inf.
    """
    if not is_passable(arc, profile):
        return math.inf
    factor = (
        profile.stair_factor if arc.steps else SLOPE_FACTORS[grade_level(arc.grade)]
    )
    congestion_factor = (
        1 + CONGESTION_WEIGHTS[profile.congestion_tolerance] * congestion
    )
    return arc.length * factor * congestion_factor
