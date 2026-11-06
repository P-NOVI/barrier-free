from enum import StrEnum

# 교통약자의 이동편의 증진법 기준 1/50, 1/12
EASY_MAX_GRADE = 1 / 50
MODERATE_MAX_GRADE = 1 / 12


class GradeLevel(StrEnum):
    EASY = "easy"
    MODERATE = "moderate"
    HARD = "hard"


def grade_level(grade: float) -> GradeLevel:
    """경사(비율, 오르막 +, 내리막 -)를 3단계로 나눈다. 내리막도 절댓값으로 판정한다."""
    steepness = abs(grade)
    if steepness <= EASY_MAX_GRADE:
        return GradeLevel.EASY
    if steepness <= MODERATE_MAX_GRADE:
        return GradeLevel.MODERATE
    return GradeLevel.HARD
