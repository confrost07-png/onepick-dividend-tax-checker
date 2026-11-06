"""배당 여력 지도(5장 현금 여력) 계산 테스트: 네 칸 나누는 경계값."""
from core import capacity_map as cm


def test_quadrant_boundaries():
    assert cm.quadrant(100, 1) == cm.SAFE        # 딱 2025만큼, 딱 1배 → 충분
    assert cm.quadrant(90, 0.5) == cm.TIGHT
    assert cm.quadrant(120, 3) == cm.ROOM
    assert cm.quadrant(101, 0.99) == cm.RISK


def test_average_fcf():
    assert cm.average_fcf({2023: 100, 2024: 200, 2025: 300}, {2023: -50, 2024: 50, 2025: None}) == (50 + 150 + 300) / 3
    assert cm.average_fcf({2025: 100}, {}) is None
    assert cm.average_fcf({2024: 100, 2025: 50}, {}) == 75


def test_svg_counts_and_clipping():
    s = cm.svg([cm.Point(120, 0.5), cm.Point(80, 3), cm.Point(500, 20)])
    assert s.startswith("<svg") and s.endswith("</svg>")
    assert f"{cm.RISK} 1곳" in s and f"{cm.SAFE} 1곳" in s and f"{cm.ROOM} 1곳" in s
    assert "범위 밖 1곳" in s
    assert s.count("<circle") == 3
