"""이벤트 스터디 통계 방법: 알려진 값으로 확인."""
import numpy as np
import pytest

from core import event_stats as st


def test_ols_cluster_matches_mean_and_inflates_se_for_clustered_data():
    y = np.array([1.0, 1.0, 1.0, -1.0, -1.0, -1.0, 2.0, 2.0])
    X = np.ones((8, 1))
    beta, se_c = st.ols_cluster(X, y, np.array(["a", "a", "a", "b", "b", "b", "c", "c"]))
    _, se_i = st.ols_cluster(X, y, np.arange(8))
    assert beta[0] == pytest.approx(y.mean()) and se_c[0] > se_i[0]


def test_benjamini_hochberg_and_signs():
    assert st.benjamini_hochberg([0.01, 0.04, 0.03, 0.5]) == pytest.approx([0.04, 0.16 / 3, 0.16 / 3, 0.5])
    z, p = st.generalized_sign(np.array([1.0] * 70 + [-1.0] * 30), 0.5)
    assert z == pytest.approx(4.0) and p < 0.001


def test_market_model_ar_removes_beta():
    rng = np.random.default_rng(1)
    m = 100 * np.cumprod(1 + rng.normal(0, 0.01, 400))
    rm = np.r_[0, m[1:] / m[:-1] - 1]
    s = 100 * np.cumprod(1 + 0.5 * rm)  # β = 0.5, α = 0
    x = st.event_ar(s, m, 300, 20, "시장모형")
    assert abs(x.ar.sum()) < 1e-9 and x.sigma < 1e-9
    assert st.event_ar(s, m, 300, 20, "시장조정").ar.sum() != pytest.approx(0, abs=1e-6)
