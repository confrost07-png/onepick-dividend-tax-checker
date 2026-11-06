"""기준선 몰림(2장) 계산 테스트: 구간 세기, 예상 곡선, 몰린 회사 수."""
import numpy as np

from core import bunching as bn


def _smooth(n=4000, seed=1):
    rng = np.random.default_rng(seed)
    return list(rng.uniform(5, 75, n))


def test_counts_drop_out_of_range():
    left, hist = bn.counts([4.9, 5.0, 5.5, 74.9, 75.0])
    assert left[0] == 5.0 and len(left) == 70
    assert hist.sum() == 3


def test_no_bunching_on_smooth_distribution():
    r = bn.estimate(_smooth(), 25.0)
    assert abs(r.excess) < 0.1 * r.above_actual


def test_shifted_firms_show_up_as_excess_and_missing():
    vals = _smooth()
    shifted = [25.5 if 22 <= v < 25 else v for v in vals]  # 기준선 아래 회사를 모두 바로 위로 옮김
    moved = sum(1 for v in vals if 22 <= v < 25)
    r = bn.estimate(shifted, 25.0)
    assert r.below_actual == 0
    assert abs(r.excess - moved) < 0.25 * moved
    assert abs(r.missing - moved) < 0.25 * moved


def test_bootstrap_interval_contains_estimate():
    vals = [25.5 if 22 <= v < 25 else v for v in _smooth(1500)]
    r = bn.bootstrap(vals, 25.0, reps=100)
    assert r.ci_low < r.excess < r.ci_high


def test_payouts_skip_deficit_and_missing():
    comp = {"a": ({2025: 30}, {2025: 100}, {}), "b": ({2025: 30}, {2025: -5}, {}), "c": ({2025: None}, {2025: 100}, {})}
    assert bn.payouts_by_year(comp, [2025]) == {2025: [30.0]}


def test_one_sided_ignores_truncation_below_threshold():
    vals = [v for v in _smooth(6000) if v >= 25]  # 회사를 고른 방식 때문에 25% 아래가 빈 경우
    r = bn.one_sided_25(vals)
    assert abs(r.excess) < 0.15 * r.above_actual


def test_one_sided_finds_spike_above_threshold():
    vals = [v for v in _smooth(6000) if v >= 25] + [25.5] * 150
    assert abs(bn.one_sided_25(vals).excess - 150) < 40
