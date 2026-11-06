"""다음 해 탈락 예측(4장) 테스트: 특징 7개 만들기, 로지스틱 회귀·AUC."""
import pytest

from core import retention as rt


def _company(d, ni, eq=1000, liab=500):
    return (d, ni, {y: (liab, eq) for y in ni})


def test_features_for_ga_route():
    d, ni, bs = _company({2022: 40, 2023: 50}, {2022: 100, 2023: 100})
    f = rt.features(d, ni, bs, 2023)
    assert f["route_na"] == 0 and f["payout"] == 50 and f["d_growth"] == pytest.approx(25)
    assert f["roe"] == 10 and f["roe_swing"] == 0 and f["debt"] == 50 and f["deficit"] == 0


def test_features_none_when_not_met():
    d, ni, bs = _company({2022: 20, 2023: 20}, {2022: 100, 2023: 100})
    assert rt.features(d, ni, bs, 2023) is None


def test_panel_marks_drop_and_reason():
    # 2023 가목 충족(50%) → 2024 배당 줄임(제2호 미충족) → 탈락
    d, ni, bs = _company({2022: 40, 2023: 50, 2024: 30}, {2022: 100, 2023: 100, 2024: 100})
    rows = rt.panel({"a": (d, ni, bs)}, [2023])
    assert len(rows) == 1 and rows[0]["drop"] == 1 and rows[0]["reason"] == "제2호 미충족"


def test_panel_keeps_retained():
    d, ni, bs = _company({2022: 40, 2023: 50, 2024: 50}, {2022: 100, 2023: 100, 2024: 100})
    assert rt.panel({"a": (d, ni, bs)}, [2023])[0]["drop"] == 0


def test_auc():
    assert rt.auc([0.9, 0.8, 0.1, 0.2], [1, 1, 0, 0]) == 1
    assert rt.auc([0.5, 0.5], [1, 0]) == 0.5
    assert rt.auc([0.1, 0.9], [1, 0]) == 0
