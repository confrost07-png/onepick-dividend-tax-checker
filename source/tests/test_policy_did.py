"""세금 제도와 배당(9장 이중차분) 테스트: 필요한 증가율, 처리군·비교군 나누기."""
import numpy as np
import pandas as pd
import pytest

from core import policy_did as pd_


def test_needed_growth_and_groups():
    # 배당성향 30%(25~40%): 나목은 10% 증가면 됨
    assert pd_.needed_growth(30, 100) == pytest.approx(0.10)
    # 배당성향 10%: 나목 25 → 150% 증가, 가목 40 → 300% → 150%
    assert pd_.needed_growth(10, 100) == pytest.approx(1.5)
    # 배당성향 20%: 25/20 − 1 = 25%
    assert pd_.needed_growth(20, 100) == pytest.approx(0.25)
    assert pd_.distance_group(45, 100) == pd_.MET
    assert pd_.distance_group(20, 100) == pd_.CLOSE
    assert pd_.distance_group(10, 100) == pd_.FAR
    assert pd_.distance_group(0, 100) == pd_.OUT
    assert pd_.distance_group(10, -5) == pd_.OUT
    assert pd_.distance_group(np.nan, 100) == pd_.OUT


def test_met_requirement():
    assert pd_.met_requirement(40, 30, 100) == 1.0          # 가목
    assert pd_.met_requirement(33, 30, 100) == 1.0          # 나목: 25% 이상, 10% 증가
    assert pd_.met_requirement(32, 30, 100) == 0.0          # 10% 미달
    assert pd_.met_requirement(45, 50, 100) == 0.0          # 배당이 줄면 제2호 미충족
    assert np.isnan(pd_.met_requirement(40, 30, -1))


def test_holder_table_uses_total_row_and_person_rule():
    rows = pd.DataFrame([
        {"corp_code": "A", "rcept_no": "1", "nm": "홍길동", "relate": "최대주주", "share_class": "보통", "trmend_shares": 100, "trmend_pct": 20},
        {"corp_code": "A", "rcept_no": "1", "nm": "계", "relate": None, "share_class": "보통", "trmend_shares": 200, "trmend_pct": 35},
        {"corp_code": "B", "rcept_no": "1", "nm": "(주)지주", "relate": "최대주주", "share_class": "보통", "trmend_shares": 100, "trmend_pct": 50},
        {"corp_code": "C", "rcept_no": "1", "nm": "김철수", "relate": "최대주주", "share_class": "보통", "trmend_shares": 100, "trmend_pct": 10},
    ])
    t = pd_.holder_table(rows).set_index("corp_code")
    assert t.loc["A", "holder_high"] == 1 and t.loc["A", "pct_common"] == 35
    assert t.loc["B", "holder_high"] == 0  # 법인
    assert t.loc["C", "holder_high"] == 0  # 개인이지만 30% 미만


def _panel(effect_close: float, effect_holder: float, n: int = 400, seed: int = 0) -> pd.DataFrame:
    """2025년에만 '가까움'·대주주 무리의 10% 증가 확률이 effect만큼 오르는 가짜 패널."""
    rng = np.random.default_rng(seed)
    rows = []
    for f in range(n):
        high = float(f % 3 == 0)
        base = rng.normal() * 0.1
        for y in range(2018, 2026):
            close = float(rng.random() < 0.5)
            prob = 0.3 + base + 0.1 * close + (y == 2025) * (effect_close * close + effect_holder * high) + 0.02 * (y - 2018)
            rows.append({"corp_code": f"C{f}", "bsns_year": y, "dist": pd_.CLOSE if close else pd_.FAR, "close": close,
                         "holder_high": high, "up10": float(rng.random() < np.clip(prob, 0, 1)),
                         **{c: rng.normal() for c in pd_.BASE_CONTROLS + pd_.EXPOSURE_CONTROLS}})
    return pd.DataFrame(rows)


def test_did_distance_recovers_effect_and_null():
    r = pd_.did_distance(_panel(0.25, 0.0), n_perm=99)
    assert r.coef == pytest.approx(0.25, abs=0.07) and r.p_perm < 0.05
    z = pd_.did_distance(_panel(0.0, 0.0, seed=2), n_perm=99)
    assert abs(z.coef) < 0.07 and z.p_perm > 0.05


def test_did_holder_recovers_effect():
    r = pd_.did_holder(_panel(0.0, 0.25, seed=3), n_perm=99)
    assert r.coef == pytest.approx(0.25, abs=0.07) and r.p_perm < 0.05
    assert r.n_treated_post == 134  # 400곳 중 3으로 나누어떨어지는 번호


def test_event_study_has_base_year_zero_and_post_effect():
    es = pd_.event_study(_panel(0.3, 0.0, n=1500, seed=4), "close").set_index("year")
    assert es.loc[pd_.BASE_YEAR, "coef"] == 0
    assert es.loc[2025, "coef"] == pytest.approx(0.3, abs=0.1)
    assert es.drop(index=2025)["coef"].abs().max() < 0.1
