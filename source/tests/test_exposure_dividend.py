"""금리·환율 노출도와 배당(8장 보조) 계산 테스트: 차입금·외화 계정 합치기."""
import numpy as np
import pandas as pd
import pytest

from core import exposure_dividend as ex


def _lines(rows):
    cols = ["corp_code", "bsns_year", "fs_div", "sj_div", "account_id", "account_nm", "thstrm_amount"]
    return pd.DataFrame(rows, columns=cols)


def test_borrowings_sums_principal_lines_only():
    lines = _lines([
        ("A", 2020, "CFS", "BS", "x", "단기차입금", 100),
        ("A", 2020, "CFS", "BS", "x", "장기차입금", 50),
        ("A", 2020, "CFS", "BS", "x", "사채할인발행차금", -5),   # 원금 아님
        ("A", 2020, "CFS", "CF", "x", "단기차입금의 순증가", 30),  # 현금흐름표
        ("A", 2020, "CFS", "BS", "x", "유동성사채", 20),
    ])
    out = ex.borrowings(lines)
    assert out["borrow_won"].tolist() == [170.0]


def test_fx_items_adds_cf_and_largest_cis_line():
    lines = _lines([
        ("A", 2020, "CFS", "CF", ex.FX_CF_IDS[0], "외화환산이익", 10),
        ("A", 2020, "CFS", "CF", "-표준계정코드 미사용-", "외화환산손실", -4),
        ("A", 2020, "CFS", "CIS", ex.FX_CIS_IDS[0], "해외사업장환산외환차이", -30),
        ("A", 2020, "CFS", "CIS", ex.FX_CIS_IDS[0], "해외사업장환산외환차이(세후)", 25),
        ("A", 2020, "CFS", "SCE", ex.FX_CIS_IDS[0], "해외사업장환산외환차이", 99),  # 자본변동표는 안 씀
    ])
    assert ex.fx_items(lines)["fx_won"].tolist() == [44.0]


def test_attach_lines_zero_when_statement_present_nan_when_absent():
    panel = pd.DataFrame({"corp_code": ["A", "A", "B"], "bsns_year": [2020, 2021, 2020], "fs_basis": ["연결", "별도", None]})
    values = pd.DataFrame({"corp_code": ["A"], "bsns_year": [2020], "fs_div": ["CFS"], "borrow_won": [7.0]})
    present = pd.DataFrame({"corp_code": ["A", "A"], "bsns_year": [2020, 2021], "fs_div": ["CFS", "OFS"], "sj_div": ["BS", "BS"]})
    out = ex.attach_lines(panel, values, present, "borrow_won")
    assert out.iloc[0] == 7.0 and out.iloc[1] == 0.0 and np.isnan(out.iloc[2])


def test_holm():
    assert ex.holm([0.01, 0.04]) == pytest.approx([0.02, 0.04])
    assert ex.holm([0.03, 0.02]) == pytest.approx([0.04, 0.04])


def test_demean_removes_both_effects():
    rng = np.random.default_rng(0)
    firm = np.repeat(np.arange(30), 6)
    year = np.tile(np.arange(6), 30)
    keep = rng.random(len(firm)) > 0.2  # 불균형
    firm, year = firm[keep], year[keep]
    v = rng.normal(size=30)[firm] + rng.normal(size=6)[year]
    assert np.abs(ex.demean(v, [firm, year])).max() < 1e-8


def _synthetic(beta: float, n_firms: int = 300, seed: int = 1) -> pd.DataFrame:
    """정답 계수(beta)를 아는 가짜 패널. 경기는 해마다 하나, 노출도는 회사마다 다르다."""
    rng = np.random.default_rng(seed)
    years = np.arange(2017, 2026)
    macro = rng.normal(size=len(years)) * 0.5
    rows = []
    for f in range(n_firms):
        base = rng.normal()
        for t, y in enumerate(years):
            e = rng.random()
            ctrl = rng.normal(size=3)
            out = base + 0.3 * t + beta * e * macro[t] + 0.2 * e + ctrl @ [0.1, 0.05, -0.1] + rng.normal() * 0.3
            rows.append((f"C{f}", y, e, macro[t], *ctrl, out))
    return pd.DataFrame(rows, columns=["corp_code", "bsns_year", "exp", "m", *ex.CONTROLS, "y"])


def test_fit_recovers_known_interaction():
    d = _synthetic(beta=-0.8)
    r = ex.fit(d, "y", "exp", "m", n_perm=200)
    assert r.coef == pytest.approx(-0.8, abs=0.1)
    assert r.p_cluster < 0.001 and r.p_perm < 0.05
    assert r.n_years == 9 and r.n_firms == 300


def test_fit_null_is_not_significant():
    r = ex.fit(_synthetic(beta=0.0, seed=3), "y", "exp", "m", n_perm=200)
    assert abs(r.coef) < 0.1 and r.p_perm > 0.05


def test_build_panel_lags_only_consecutive_years_and_ranks_within_year():
    panel = pd.DataFrame({
        "corp_code": ["A", "A", "A", "B", "B"],
        "group": "x",
        "bsns_year": [2018, 2019, 2021, 2018, 2019],
        "ni_owner_won": [10, 12, 11, 5, 4], "assets_won": [100, 110, 120, 50, 50],
        "d_won": [3, 4, 4, 1, 1], "dps_common_won": [100, 120, 120, 50, 40],
        "borrow_won": [10, 20, 0, 25, 5], "fx_won": [1, 1, 1, 0, 0],
    })
    macro = pd.DataFrame({"base_rate_chg": [0.25, -0.5, 0.0, 0.1], "ktb3y_chg": [0, 0, 0, 0], "usdkrw_growth": [1, 2, 3, 4]},
                         index=pd.Index([2018, 2019, 2020, 2021], name="year"))
    p = ex.build_panel(panel, macro).set_index(["corp_code", "bsns_year"])
    assert p.loc[("A", 2019), "dir"] == 1 and p.loc[("B", 2019), "dir"] == -1
    assert np.isnan(p.loc[("A", 2021), "dir"])  # 2020이 없어 전년 비교 안 함
    # 2019 금리 노출: A 10/100 = 0.10, B 25/50 = 0.50 → A 0, B 1
    assert p.loc[("A", 2019), "rate_exp"] == 0 and p.loc[("B", 2019), "rate_exp"] == 1
    assert p.loc[("A", 2019), "base_rate_chg"] == -0.5
    assert p.loc[("A", 2019), "base_rate_chg_prev"] == 0.25 and p.loc[("A", 2019), "base_rate_chg_next"] == 0.0
