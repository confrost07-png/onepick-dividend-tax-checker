"""데이터 이야기 보고서: 확인용 SQL이 화면 값과 같고, 요약 장·장 11개와 부록의 모든 조합이 빠짐없이 들어가는지."""
import pytest

from api import data
from scripts import report_story_pdf as rp
from scripts import story_checks as sc


@pytest.fixture(scope="module")
def screen():
    try:
        data.funnel()
    except Exception:  # noqa: BLE001
        pytest.skip("PostgreSQL에 연결할 수 없음")
    return rp.screen_data()


def test_every_chapter_has_a_check():
    assert {c.ch for c in sc.CHECKS} == set(range(1, 12))


def test_checks_match_screen(screen):
    outs = sc.run(screen)
    assert [f"{o.check.ch}장 {o.check.what}" for o in outs if not o.same] == []


def test_report_has_all_chapters_and_combinations(screen):
    html = rp.build(screen, sc.run(screen))
    for no in range(1, 12):
        assert f"<span class='ch-no'>{no}장</span>" in html
    for label in rp.LABELS:
        assert html.count(f"<span class='tag'>{label}</span>") >= 11
    assert html.count("<span class='result-tag'>결과</span>") >= 11
    assert "한눈에 보는 <em>결론</em>" in html
    a = screen["analysis"]
    assert f"모든 조건 {len(screen['events']['summary'])}개" in html
    assert f"상관 {len(a['macro']['corr'])}칸 전부" in html
    assert f"검정 {sum(len(v) for v in a['behavior']['fits'].values())}개 전부" in html


def test_extra_numbers_match_their_scripts(screen):
    """2장 몰림 크기와 9장 제도 전 점검은 화면 글과 같은 코드에서 나온다(2026-10-29 · 11-03 결과 문서와 같은 값)."""
    b = screen["extra"]["bunching"][2025]
    assert round(b.excess) == 69 and b.ci_low > 0
    assert all(r.ci_low <= 0 for y, r in screen["extra"]["bunching"].items() if y < 2025)
    pt = screen["extra"]["pretrend"]
    assert round(pt["wald_p"], 2) == 0.13 and round(pt["did_trend"]["coef"], 1) == 9.0
    own = next(x for x in screen["analysis"]["behavior"]["fits"]["policy"] if x["role"] == "primary" and x["name"].startswith("개인 최대주주"))
    assert round(pt["did_plain"]["coef"], 1) == round(own["coef"] * 100, 1)
