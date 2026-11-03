import math
from dataclasses import replace

import pytest

from core.cost import SLOPE_FACTORS, STEEP_FACTORS, TRAIL_FACTORS, arc_cost
from core.graph import Arc, Trail
from core.profiles import CONGESTION_WEIGHTS, PRESETS, CongestionTolerance
from core.slope import GradeLevel

LENGTH = 100.0
FLAT = Arc(
    edge_id=0,
    source=0,
    target=1,
    length=LENGTH,
    grade=0.0,
    steps=False,
    wheelchair_ok=True,
    walk_ok=True,
)
STAIRS_UP = replace(FLAT, grade=0.3, steps=True, wheelchair_ok=False)
STAIRS_DOWN = replace(STAIRS_UP, grade=-0.3)


def test_flat_arc_costs_its_length() -> None:
    assert arc_cost(FLAT, PRESETS["general"]) == LENGTH


def test_slope_factor_by_grade_level() -> None:
    arc = replace(FLAT, grade=0.05)
    assert (
        arc_cost(arc, PRESETS["general"]) == LENGTH * SLOPE_FACTORS[GradeLevel.MODERATE]
    )


@pytest.mark.parametrize(
    ("grade", "factor"),
    [
        (0.12, SLOPE_FACTORS[GradeLevel.HARD]),
        (0.15, SLOPE_FACTORS[GradeLevel.HARD]),
        (0.2, STEEP_FACTORS[1][1]),
        (-0.2, STEEP_FACTORS[1][1]),
        (0.3, STEEP_FACTORS[0][1]),
    ],
)
def test_steeper_grades_cost_more_for_general(grade: float, factor: float) -> None:
    arc = replace(FLAT, grade=grade)
    assert arc_cost(arc, PRESETS["general"]) == pytest.approx(LENGTH * factor)


def test_steep_factors_grow_with_grade() -> None:
    factors = [factor for _, factor in reversed(STEEP_FACTORS)]
    assert SLOPE_FACTORS[GradeLevel.HARD] < factors[0] < factors[1]


@pytest.mark.parametrize("trail", list(Trail))
def test_trail_factor_multiplies_slope_and_stairs(trail: Trail) -> None:
    profile = PRESETS["general"]
    steep = replace(FLAT, grade=0.2, trail=trail)
    stairs = replace(STAIRS_UP, grade=0.0, trail=trail)
    assert arc_cost(steep, profile) == pytest.approx(
        LENGTH * STEEP_FACTORS[1][1] * TRAIL_FACTORS[trail]
    )
    assert arc_cost(stairs, profile) == pytest.approx(
        LENGTH * profile.stair_factor * TRAIL_FACTORS[trail]
    )


def test_mountain_trail_costs_more_than_hiking_trail() -> None:
    assert 1 < TRAIL_FACTORS[Trail.HIKING] < TRAIL_FACTORS[Trail.MOUNTAIN]


@pytest.mark.parametrize("grade", [0.09, -0.09])
def test_grade_over_limit_is_impassable_both_directions(grade: float) -> None:
    arc = replace(FLAT, grade=grade)
    assert math.isinf(arc_cost(arc, PRESETS["manual_wheelchair"]))
    assert math.isfinite(arc_cost(arc, PRESETS["power_wheelchair"]))


@pytest.mark.parametrize(
    "preset", ["manual_wheelchair", "power_wheelchair", "stroller"]
)
def test_stairs_impassable_for_wheeled_presets(preset: str) -> None:
    assert math.isinf(arc_cost(STAIRS_UP, PRESETS[preset]))
    assert math.isinf(arc_cost(STAIRS_DOWN, PRESETS[preset]))


@pytest.mark.parametrize("preset", ["crutches", "elderly", "general"])
def test_stairs_use_larger_of_stair_and_slope_factor(preset: str) -> None:
    profile = PRESETS[preset]
    gentle = replace(STAIRS_UP, grade=0.05)
    assert arc_cost(gentle, profile) == LENGTH * max(
        profile.stair_factor, SLOPE_FACTORS[GradeLevel.MODERATE]
    )
    assert arc_cost(STAIRS_UP, profile) == LENGTH * max(
        profile.stair_factor, STEEP_FACTORS[0][1]
    )


def test_stairs_direction_follows_grade_sign() -> None:
    down_only = replace(PRESETS["general"], stairs_up=False)
    assert math.isinf(arc_cost(STAIRS_UP, down_only))
    assert math.isfinite(arc_cost(STAIRS_DOWN, down_only))


def test_wheelchair_ok_false_blocks_only_wheelchair_access_presets() -> None:
    arc = replace(FLAT, wheelchair_ok=False)
    assert math.isinf(arc_cost(arc, PRESETS["manual_wheelchair"]))
    assert math.isinf(arc_cost(arc, PRESETS["stroller"]))
    assert math.isfinite(arc_cost(arc, PRESETS["crutches"]))


def test_walk_ok_false_blocks_every_preset() -> None:
    arc = replace(FLAT, walk_ok=False)
    for profile in PRESETS.values():
        assert math.isinf(arc_cost(arc, profile))


@pytest.mark.parametrize("tolerance", list(CongestionTolerance))
def test_congestion_penalty_by_tolerance(tolerance: CongestionTolerance) -> None:
    profile = replace(PRESETS["general"], congestion_tolerance=tolerance)
    expected = LENGTH * (1 + CONGESTION_WEIGHTS[tolerance])
    assert arc_cost(FLAT, profile, congestion=1.0) == pytest.approx(expected)


def test_congestion_penalty_order() -> None:
    weights = CONGESTION_WEIGHTS
    assert weights[CongestionTolerance.AVOID] > weights[CongestionTolerance.NORMAL]
    assert (
        weights[CongestionTolerance.NORMAL] > weights[CongestionTolerance.IGNORE] == 0
    )
