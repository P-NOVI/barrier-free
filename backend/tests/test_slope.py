import pytest

from core.slope import GradeLevel, grade_level


@pytest.mark.parametrize(
    ("grade", "expected"),
    [
        (0.0, GradeLevel.EASY),
        (0.02, GradeLevel.EASY),
        (0.0201, GradeLevel.MODERATE),
        (1 / 12, GradeLevel.MODERATE),
        (0.0834, GradeLevel.HARD),
        (-0.02, GradeLevel.EASY),
        (-0.05, GradeLevel.MODERATE),
        (-0.1, GradeLevel.HARD),
    ],
)
def test_grade_level_boundaries(grade: float, expected: GradeLevel) -> None:
    assert grade_level(grade) == expected
