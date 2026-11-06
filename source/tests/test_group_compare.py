"""두 집단 비교 테스트: 가운데 값 차이, 결측 빼기, 부트스트랩 범위."""
import math

import numpy as np
import pytest

from core import group_compare as gc


def test_median_diff_ignores_missing():
    d = gc.median_diff([1, 2, 3, None], [0, 0, 0, float("nan")], reps=50)
    assert (d.a, d.b, d.diff, d.n_a, d.n_b) == (2, 0, 2, 3, 3)
    assert d.low <= d.diff <= d.high


def test_share_diff_in_percent():
    d = gc.share_diff([True, True, False, False], [False] * 4, reps=50)
    assert d.a == pytest.approx(50) and d.b == 0 and d.diff == pytest.approx(50)


def test_logistic_recovers_known_coefficients():
    rng = np.random.default_rng(0)
    x = rng.normal(size=(20000, 2))
    true = np.array([-0.5, 1.0, -2.0])
    p = 1 / (1 + np.exp(-(true[0] + x @ true[1:])))
    y = (rng.uniform(size=len(p)) < p).astype(float)
    terms = gc.logistic(x, y, ["a", "b"])
    assert [t.name for t in terms] == ["상수항", "a", "b"]
    for t, b in zip(terms, true):
        assert t.coef == pytest.approx(b, abs=0.08)
    assert terms[1].odds == pytest.approx(math.exp(terms[1].coef))
    assert terms[1].odds_low < terms[1].odds < terms[1].odds_high
    assert terms[2].p < 1e-6


def test_logistic_no_effect_has_large_p():
    rng = np.random.default_rng(1)
    x = rng.normal(size=(2000, 1))
    y = (rng.uniform(size=2000) < 0.3).astype(float)
    assert gc.logistic(x, y, ["noise"])[1].p > 0.01
