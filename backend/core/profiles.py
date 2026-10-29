from dataclasses import dataclass
from enum import StrEnum

from core.slope import MODERATE_MAX_GRADE

POWER_WHEELCHAIR_MAX_GRADE = 1 / 8

# 계단·혼잡 배율은 초안 값이다. evaluation/ 결과를 보고 조정한다.
STAIR_FACTOR_HIGH = 5.0
STAIR_FACTOR_MEDIUM = 3.0
STAIR_FACTOR_NONE = 1.0


class CongestionTolerance(StrEnum):
    AVOID = "avoid"
    NORMAL = "normal"
    IGNORE = "ignore"


# 혼잡도(0~1)가 1일 때 구간 비용이 (1 + 가중치)배가 된다.
CONGESTION_WEIGHTS: dict[CongestionTolerance, float] = {
    CongestionTolerance.AVOID: 1.0,
    CongestionTolerance.NORMAL: 0.5,
    CongestionTolerance.IGNORE: 0.0,
}


@dataclass(frozen=True)
class Profile:
    max_grade: float | None
    stairs_up: bool
    stairs_down: bool
    stair_factor: float
    needs_wheelchair_access: bool
    congestion_tolerance: CongestionTolerance


PRESETS: dict[str, Profile] = {
    "manual_wheelchair": Profile(
        max_grade=MODERATE_MAX_GRADE,
        stairs_up=False,
        stairs_down=False,
        stair_factor=STAIR_FACTOR_NONE,
        needs_wheelchair_access=True,
        congestion_tolerance=CongestionTolerance.AVOID,
    ),
    "power_wheelchair": Profile(
        max_grade=POWER_WHEELCHAIR_MAX_GRADE,
        stairs_up=False,
        stairs_down=False,
        stair_factor=STAIR_FACTOR_NONE,
        needs_wheelchair_access=True,
        congestion_tolerance=CongestionTolerance.AVOID,
    ),
    "stroller": Profile(
        max_grade=MODERATE_MAX_GRADE,
        stairs_up=False,
        stairs_down=False,
        stair_factor=STAIR_FACTOR_NONE,
        needs_wheelchair_access=True,
        congestion_tolerance=CongestionTolerance.NORMAL,
    ),
    "crutches": Profile(
        max_grade=POWER_WHEELCHAIR_MAX_GRADE,
        stairs_up=True,
        stairs_down=True,
        stair_factor=STAIR_FACTOR_HIGH,
        needs_wheelchair_access=False,
        congestion_tolerance=CongestionTolerance.AVOID,
    ),
    "elderly": Profile(
        max_grade=POWER_WHEELCHAIR_MAX_GRADE,
        stairs_up=True,
        stairs_down=True,
        stair_factor=STAIR_FACTOR_MEDIUM,
        needs_wheelchair_access=False,
        congestion_tolerance=CongestionTolerance.NORMAL,
    ),
    "general": Profile(
        max_grade=None,
        stairs_up=True,
        stairs_down=True,
        stair_factor=STAIR_FACTOR_NONE,
        needs_wheelchair_access=False,
        congestion_tolerance=CongestionTolerance.NORMAL,
    ),
}

DEFAULT_PRESET = "general"
