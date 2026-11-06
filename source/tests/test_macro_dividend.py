"""경기와 배당(8장) 계산 테스트: 연간 합·평균, 덜 찬 해 빼기, 순열 검정."""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from core import macro_dividend as md


def _macro(series, cycle, starts, values):
    return pd.DataFrame({"series": series, "cycle": cycle, "period_start": starts, "value": values})


def _full_macro(years=(2019, 2020)):
    parts = []
    for name, series, *_ in md.ANNUAL:
        cycle = "Q" if series.endswith("_q") else "M"
        step = 3 if cycle == "Q" else 1
        starts = [date(y, m, 1) for y in years for m in range(1, 13, step)]
        parts.append(_macro(series, cycle, starts, [float(s.year - 2018) for s in starts]))
    return pd.concat(parts)


def test_macro_annual_sums_means_and_drops_partial_year():
    m = _full_macro()
    partial = _macro("base_rate_m", "M", [date(2021, 1, 1)], [9.0])  # 1월만 있는 해
    out = md.macro_annual(pd.concat([m, partial]))
    assert list(out.index) == [2019, 2020]
    assert out.loc[2020, "base_rate"] == 2.0 and out.loc[2020, "current_account"] == 24.0
    assert out.loc[2020, "gdp_growth"] == pytest.approx(100.0)  # 4 → 8
    assert out.loc[2020, "base_rate_chg"] == 1.0


def test_panel_needs_consecutive_years_and_positive_dps_for_growth():
    div = pd.DataFrame({"corp_code": ["A", "A", "A", "B", "B"], "bsns_year": [2018, 2019, 2021, 2018, 2019],
                        "dps_common_won": [100, 150, 200, 0, 50]})
    p = md.panel(div).set_index(["corp_code", "bsns_year"])
    assert p.loc[("A", 2019), "dps_growth"] == pytest.approx(50.0)
    assert ("A", 2021) not in p.index  # 2020이 비어 이어지지 않음
    assert p.loc[("B", 2019), "dps_change"] == 50 and np.isnan(p.loc[("B", 2019), "dps_growth"])


def test_dividend_annual_excludes_only_from_total():
    div = pd.DataFrame({"corp_code": ["A", "B", "A", "B"], "bsns_year": [2018, 2018, 2019, 2019],
                        "d_dart_won": [1e12, 0, 9e15, 2e12], "dps_common_won": [100, 0, 100, 10]})
    yields = pd.DataFrame({"corp_code": ["A"], "bsns_year": [2019], "yield_pct": [2.5]})
    out = md.dividend_annual(div, yields, exclude={("A", 2019)})
    assert out.loc[2019, "total_tril"] == pytest.approx(2.0)
    assert out.loc[2019, "payer_share"] == 100.0 and out.loc[2018, "payer_share"] == 50.0
    assert out.loc[2019, "dps_up_share"] == 50.0 and out.loc[2019, "yield_median"] == 2.5


def test_corr_perfect_and_constant():
    r = md.corr([1, 2, 3, 4, 5], [2, 4, 6, 8, 10], n_perm=500)
    assert r["r"] == pytest.approx(1.0) and r["p"] < 0.05 and r["n"] == 5
    assert np.isnan(md.corr([1, 2, 3], [5, 5, 5])["r"])
    assert md.corr([1, np.nan, 3, 4], [1, 2, 3, 4])["n"] == 3


def test_macro_window_q1_compares_same_quarter():
    m = _full_macro()
    q1 = md.macro_window(m, range(1, 4))
    assert q1.loc[2020, "current_account"] == 6.0  # 1~3월 합계: 2 × 3
    assert q1.loc[2020, "gdp_real"] == 2.0  # 1분기 하나만
    assert q1.loc[2020, "gdp_growth"] == pytest.approx(100.0)


def test_macro_lagged_puts_values_on_dividend_year():
    lag = md.macro_lagged(_full_macro())
    assert lag["prev"].loc[2020, "base_rate"] == lag["same"].loc[2019, "base_rate"]
    assert lag["decision"].loc[2019, "base_rate"] == 2.0  # 2019 사업연도 ← 2020년 1~3월
