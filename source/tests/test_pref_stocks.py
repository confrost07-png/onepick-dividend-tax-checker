"""우선주: 상장 우선주 찾기(source/scripts/collect_pref_stocks.py), 우선주 회사 자료, 챗봇 인식·계산."""
from datetime import date

import pytest

from core.chat_parse import validate_holdings
from scripts import collect_pref_stocks as cps


def _resp(name, day):
    return f'<chartdata symbol="x" name="{name}" count="1"><item data="{day}|1|1|1|1|1" /></chartdata>'


def test_candidates_keep_first_five_digits():
    assert cps.candidates("005930") == ["005935", "005937", "005939", "00593K", "00593L", "00593M", "00593N"]


def test_rows_keep_only_preferred_names_and_mark_old_ones():
    answers = {"005935": _resp("삼성전자우", "20261102"), "000885": _resp("한화우", "20250714"),
               "00088K": _resp("한화3우B", "20261102"), "005937": _resp("삼성전자", "20261102")}  # 이름이 우선주가 아니면 뺀다
    got = cps.rows([{"corp_code": "A", "stock_code": "005930"}, {"corp_code": "B", "stock_code": "000880"}],
                   get=lambda code: answers.get(code, ""))
    by = {r["pref_code"]: r for r in got}
    assert set(by) == {"005935", "000885", "00088K"}
    assert by["005935"]["status"] == cps.LISTED and by["000885"]["status"] == cps.GONE
    assert by["000885"]["last_trade_date"] == date(2025, 7, 14)


def test_company_update_lists_only_listed():
    found = [{"corp_code": "A", "pref_code": "005935", "pref_name": "삼성전자우", "status": cps.LISTED},
             {"corp_code": "B", "pref_code": "000885", "pref_name": "한화우", "status": cps.GONE}]
    out = {c: (codes, st) for codes, st, c in cps.company_update(found, ["A", "B", "C"])}
    assert out["A"] == ("005935 삼성전자우", "상장 우선주 1종목")
    assert out["B"][0] is None and "거래 없음" in out["B"][1]
    assert out["C"] == (None, "상장 우선주 없음")


def test_uncomputable_preferred_is_explained_not_guessed():
    known = {"한화": "한화"}
    r = validate_holdings([("한화3우B", 10)], known)
    assert r.code == "preferred" and "한화의 우선주" in r.error and "보통주(한화)" in r.error


def test_computable_preferred_is_recognized():
    known = {"삼성전자": "삼성전자", "삼성전자우": "삼성전자우"}
    r = validate_holdings([("삼성전자우", 100)], known)
    assert r.ok and [(h.company, h.shares) for h in r.value] == [("삼성전자우", 100)]


@pytest.fixture(scope="module")
def api_prefs():
    from api import data
    try:
        data.funnel()
    except Exception:  # noqa: BLE001
        pytest.skip("PostgreSQL에 연결할 수 없음")
    for f in (data.companies, data.prefs, data.name_index):  # 앞선 테스트가 바꿔 둔 캐시를 지우고 실제 DB로 다시 읽는다
        f.cache_clear()
    book, skipped = data.prefs()
    if not book:
        pytest.skip("상장 우선주 목록이 아직 없음 (scripts.collect_pref_stocks)")
    return data, book, skipped


def test_preferred_uses_preferred_dps_and_company_judgement(api_prefs):
    data, book, _ = api_prefs
    name, c = next(iter(sorted(book.items())))
    base = data.companies()[c.pref_of]
    assert (c.b2025, c.d2025, c.kind_2025) == (base.b2025, base.d2025, base.kind_2025)  # 판정은 회사 단위
    out = data.checkup({name: 100}, 0, 0, 0, 30_000_000, False)
    s = out["stocks"][0]
    assert s["name"] == name and s["pref_of"] == base.name
    assert s["special"] + s["held"] <= (c.dps_2025_final + c.dps_2026_interim) * 100


def test_multi_class_preferred_is_skipped(api_prefs):
    _, book, skipped = api_prefs
    assert not set(book) & set(skipped)


def test_class_amounts_file_has_source_for_every_row():
    import csv
    from core.company_repo import PREF_BY_CLASS, pref_by_class
    rows = list(csv.DictReader(PREF_BY_CLASS.open(encoding="utf-8")))
    assert rows and all(r["rcept_no"].isdigit() and len(r["rcept_no"]) == 14 and r["where"] for r in rows)
    assert pref_by_class()["000157"] == 4000  # 두산2우B: 사업보고서 주석


def test_multi_class_uses_report_amounts_and_keeps_half_won(api_prefs):
    data, book, skipped = api_prefs
    if "CJ4우(전환)" in book:
        assert book["CJ4우(전환)"].dps_2025_final == 3300 and book["CJ우"].dps_2025_final == 3350
    if "두산2우B" in skipped:  # 종목별 표가 없을 때: 2026 분기배당이 종목별로 얼마인지 가를 수 없음
        assert "2026" in skipped["두산2우B"]
    if "한국금융지주우" in book:
        out = data.checkup({"한국금융지주우": 100}, 0, 0, 0, 30_000_000, False)
        assert out["stocks"][0]["special"] + out["stocks"][0]["held"] in (875_150, 0)  # 8,751.5원 × 100주


def test_match_class_picks_the_listed_preferred_row():
    from core.company_repo import match_class
    daishin = [{"class_name": "우선주", "class_kind": "1우선주", "dps_won": 1250},
               {"class_name": "우선주", "class_kind": "2우선주", "dps_won": 1200},
               {"class_name": "상환전우선주", "class_kind": "5우선주", "dps_won": 3850}]
    assert match_class("대신증권우", daishin)["dps_won"] == 1250
    assert match_class("대신증권2우B", daishin)["dps_won"] == 1200
    hanwha = [{"class_name": "제1우선주 (한화우)", "class_kind": "우선주", "dps_won": 1150},
              {"class_name": "제3우선주 (한화3우B)", "class_kind": "우선주", "dps_won": 1150}]
    assert match_class("한화3우B", hanwha)["class_name"].endswith("(한화3우B)")
    doosan = [{"class_name": "두산우", "class_kind": "종류주식", "dps_won": 4050},
              {"class_name": "두산2우B", "class_kind": "종류주식", "dps_won": 4000}]
    assert match_class("두산2우B", doosan)["dps_won"] == 4000 and match_class("두산우", doosan)["dps_won"] == 4050
    assert match_class("하이트진로2우B", [{"class_name": "하이트진로 우", "class_kind": "우선주", "dps_won": 750}])["dps_won"] == 750
    two_plain = [{"class_name": "우선주", "class_kind": "우선주", "dps_won": 1}, {"class_name": "우선주", "class_kind": "우선주", "dps_won": 2}]
    assert match_class("가나우", two_plain) is None  # 가를 수 없으면 짐작하지 않는다


def test_notice_class_table_agrees_with_report_and_single_column(api_prefs):
    """세 출처 대조: 공시 종목별 표 = 사업보고서 원문(CSV) = 공시의 우선주 한 칸(우선주 1종목 회사)."""
    from core import db
    from core.company_repo import dps_from_decisions, pref_by_class
    data, book, _ = api_prefs
    by_code = {c.pref_code: c for c in book.values()}
    if not any(c.sources[-1].endswith("(raw.dividend_decision_class)") for c in book.values()):
        pytest.skip("종목별 표가 아직 없음 (scripts.collect_pref_dividend_class)")
    for code, won in pref_by_class().items():
        assert by_code[code].dps_2025_final == won, code
    with db.connect(db.database_url()) as conn:
        one = dps_from_decisions(conn, "dps_pref_won")
    per_corp = {}
    for c in book.values():
        per_corp.setdefault(c.corp_code, []).append(c)
    for corp, cs in per_corp.items():
        if len(cs) == 1:
            assert (cs[0].dps_2025_final, cs[0].dps_2026_interim) == (one[corp]["final"], one[corp]["interim"]), cs[0].name
    assert book["두산2우B"].dps_2026_interim == 2000 and book["두산우"].dps_2026_interim == 2000  # 2026 분기 1,000원 × 2번
    assert (book["JW중외제약우"].dps_2025_final, book["JW중외제약2우B"].dps_2025_final) == (675, 650)
