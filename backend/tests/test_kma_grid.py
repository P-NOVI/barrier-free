import pytest

from core.kma_grid import to_grid


@pytest.mark.parametrize(
    ("lat", "lon", "grid"),
    [
        (37.5665, 126.9780, (60, 127)),  # 서울시청
        (35.1796, 129.0756, (98, 76)),  # 부산시청
        (33.4996, 126.5312, (53, 38)),  # 제주시청
    ],
)
def test_known_places(lat: float, lon: float, grid: tuple[int, int]) -> None:
    assert to_grid(lat, lon) == grid


def test_outside_grid_is_rejected() -> None:
    with pytest.raises(ValueError):
        to_grid(35.68, 139.69)
