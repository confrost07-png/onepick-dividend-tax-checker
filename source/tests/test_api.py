"""새 화면용 API (source/api/main.py). 가상 회사(C사·E사)로 돌리고, DB가 있어야 하는 것은 DB가 없으면 건너뛴다."""
import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from api import data, main  # noqa: E402
from core import company_repo, sample_data  # noqa: E402
from core.faq_search import FaqSearch  # noqa: E402
from core.law_search import LawSearch  # noqa: E402
from core.virtual_cases import COMPANIES as VIRTUAL  # noqa: E402


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(data, "companies", lambda: VIRTUAL)
    monkeypatch.setattr(data, "prefs", lambda: ({}, {}))
    monkeypatch.setattr(data, "name_index", lambda: company_repo.name_index(VIRTUAL))
    monkeypatch.setattr(data, "law", lambda: LawSearch.from_files(embed=None))
    monkeypatch.setattr(data, "faq", lambda: FaqSearch.from_files(embed=None))
    return TestClient(main.app)


def parse(client, kind, text, **kw):
    return client.post("/api/chat/parse", json={"kind": kind, "text": text, **kw}).json()


def test_parse_reads_each_step_by_rules(client):
    assert parse(client, "holdings", "C사 300주")["value"] == [{"company": "C사", "shares": 300}]
    assert parse(client, "amount", "1500만 원")["value"] == 15_000_000
    assert parse(client, "amount", "모름") == {"ok": True, "value": None, "error": "", "by": "규칙"}
    assert parse(client, "other_dividend", "500만 원", dividend_type="foreign")["value"] == {"domestic": 0, "foreign": 5_000_000}
    assert parse(client, "yesno", "없어요")["value"] is False
    assert parse(client, "base", "근로소득 없음")["value"] == 0


def test_parse_asks_again_when_unreadable(client):
    r = parse(client, "yesno", "예전엔 있었는데 지금은 없어요")
    assert r["ok"] is False and "하나로" in r["error"]


def test_tax_and_stock_questions_get_fixed_reply(client):
    r = parse(client, "amount", "절세하려면 어떻게 해야 해?")
    assert r["guard"] and r["consult"] is True
    r = parse(client, "holdings", "C사 주가 오를까?")
    assert r["guard"] and r["consult"] is False


def test_input_longer_than_limit_is_rejected(client):
    assert client.post("/api/chat/parse", json={"kind": "amount", "text": "1" * 201}).status_code == 422


def test_checkup_returns_headline_and_tax_rows(client):
    r = client.post("/api/checkup", json={"holdings": [{"company": "C사", "shares": 3000}], "interest": 15_000_000,
                                          "other_domestic": 20_000_000, "other_foreign": 0, "base": 60_000_000}).json()
    assert r["headline"].startswith("보유 1종목 중")
    assert r["stocks"][0]["name"] == "C사" and r["stocks"][0]["shares"] == 3000
    assert r["tax"]["status"] and r["notes"][0] == sample_data.HOLDING_ASSUMPTION


def test_checkup_accepts_preferred_stock(client, monkeypatch):
    """챗봇이 읽은 우선주가 계산 단계에서 '찾지 못했어요'로 막히지 않는다 (우선주는 data.prefs에만 있음)."""
    from dataclasses import replace
    pref = replace(VIRTUAL["C사"], name="C사우")
    monkeypatch.setattr(data, "prefs", lambda: ({"C사우": pref}, {}))
    r = client.post("/api/checkup", json={"holdings": [{"company": "C사우", "shares": 3000}], "base": 30_000_000})
    assert r.status_code == 200 and r.json()["stocks"][0]["name"] == "C사우"


def test_checkup_rejects_unknown_company(client):
    r = client.post("/api/checkup", json={"holdings": [{"company": "없는회사", "shares": 1}]})
    assert r.status_code == 422


def test_evidence_is_original_text(client):
    labels = [e["label"] for e in client.get("/api/law/evidence").json()]
    assert labels == ["조세특례제한법 제104조의27①", "조세특례제한법 제104조의27②", "조세특례제한법 제104조의27③"]


def test_law_search_returns_original_passages(client):
    r = client.get("/api/law/search", params={"q": "분리과세 신청"}).json()
    assert r["notice"] and all(h["by"] == "글자 검색" for h in r["hits"])


def _db_or_skip():
    try:
        data.funnel()
    except Exception:  # noqa: BLE001
        pytest.skip("PostgreSQL에 연결할 수 없음")


def test_funnel_adds_up_to_judgement_counts():
    _db_or_skip()
    f = data.funnel()
    counts = company_repo.judgement_counts()
    assert f["ga"] + f["na"] + f["na_deficit"] == counts["충족"]
    assert f["fail2"] + f["fail3"] == counts["미충족"]
    assert f["hold_missing"] + f["hold_zero"] == counts["판정 보류"]


def test_every_company_view_builds():
    """B(2025)를 비워 둔 판정 보류 회사도 회사 보기가 깨지지 않는다."""
    _db_or_skip()
    views = [data.company(c.stock_code) for c in data.companies().values()]
    assert len(views) == len(data.companies()) and all(v["status"] for v in views)


def test_analysis_has_no_company_names():
    _db_or_skip()
    a = data.analysis()
    assert set(a["event"]["curves"]) == set(data.EVENT_KINDS)
    names = set(company_repo.load())
    flat = str(a)
    assert not any(n in flat for n in names if len(n) >= 3)


def test_events_include_every_condition_and_methods():
    _db_or_skip()
    e = data.events()
    keys = {(r["kind"], r["basis"], r["ret"], r["sample"], r["window"]) for r in e["summary"]}
    assert ("주당배당금 증가", "공시일", "배당 포함", "자본 변동 겹침 제외", 60) in keys
    assert any(k.startswith("감자") or k.startswith("무상증자") for k, *_ in keys)
    assert e["methods"] is None or e["methods"]["tests"]


def test_movement_frames_are_full_years_without_names():
    _db_or_skip()
    m = data.movement()
    assert max(int(y) for y in m["frames"]) <= data.LAST_FULL_YEAR
    assert all(isinstance(row[0], int) for rows in m["frames"].values() for row in rows)


@pytest.mark.parametrize("amount", [0, 1, 19_999_999, 20_000_000, 20_000_001, 300_000_001, 5_000_000_001])
def test_separate_tax_steps_add_up_to_engine(client, amount):
    from core import tax
    r = client.get("/api/tax/separate", params={"amount": amount}).json()
    assert r["tax"] == tax.separate_tax(amount)
    assert sum(s["tax"] for s in r["steps"]) == r["tax"]


def test_law_passages_are_original_text(client):
    import json
    from pathlib import Path
    stored = json.loads((Path(__file__).resolve().parents[2] / "data" / "processed" / "law" / "articles.json").read_text())["passages"]
    got = client.get("/api/law/passages").json()
    assert [p["text"] for p in got] == [p["text"] for p in stored]


def test_column_cites_only_stored_law_passages(client):
    """금융 상식 칼럼(app/web/src/columns/unit*.ts)이 붙이는 조문 이름이 모두 원문 파일에 있다."""
    import re
    from pathlib import Path
    web = Path(__file__).resolve().parents[2] / "app" / "web" / "src"
    src = "".join(f.read_text(encoding="utf-8") for f in [web / "column.ts", *sorted((web / "columns").glob("unit*.ts"))])
    cited = {c for block in re.findall(r"laws: \[([^\]]*)\]", src) for c in re.findall(r"'([^']+)'", block)}
    stored = {p["label"] for p in client.get("/api/law/passages").json()}
    assert cited and cited <= stored, cited - stored


def test_column_has_isa_and_irp_episodes():
    """금융 상식 칼럼에 ISA·IRP 글이 단원 목록에 올라 있고, 글마다 그림 도구가 화면에 이어져 있다."""
    import re
    from pathlib import Path
    web = Path(__file__).resolve().parents[2] / "app" / "web" / "src"
    units = re.search(r"export const UNITS = \[(.*?)\n\]", (web / "column.ts").read_text(encoding="utf-8"), re.S).group(1)
    assert "ids: ['isa', 'irp']" in units
    episodes = (web / "columns" / "unit12.ts").read_text(encoding="utf-8")
    assert "id: 'isa'" in episodes and "id: 'irp'" in episodes
    page = (web / "pages" / "Column.tsx").read_text(encoding="utf-8")
    assert "isabox: IsaBox" in page and "pension: PensionCredit" in page


def test_column_spread_matches_event_summary():
    """칼럼의 사례 분포가 데이터 이야기 6장 주 조건(사례 수·가운데 값)과 같다."""
    _db_or_skip()
    import statistics
    v = data.spread_example()["values"]
    main = next(r for r in data.events()["summary"] if (r["kind"], r["basis"], r["ret"], r["sample"], r["window"])
                == ("주당배당금 증가", "공시일", "배당 포함", "자본 변동 겹침 제외", 60))
    assert len(v) == main["n"] and round(statistics.median(v), 2) == round(main["median"], 2)


def test_column_race_example_has_60_days():
    _db_or_skip()
    r = data.race_example(3)
    assert len(r["path"]) == 61 and r["path"][0][0] == 0 and "corp" not in str(r)


def test_question_in_checkup_shows_fixed_faq_answer(client):
    """점검 중 금융 상식 질문을 하면 고정 답변 문장을 그대로 돌려주고, 값으로 읽지 않는다."""
    import json
    from pathlib import Path
    items = json.loads((Path(__file__).resolve().parents[2] / "data" / "processed" / "faq" / "finance_faq.json").read_text(encoding="utf-8"))["items"]
    item = next(i for i in items if i["id"] == "ex_dividend")
    r = parse(client, "amount", item["examples"][0])
    assert r["ok"] is False and r["question"] is True
    assert r["faq"]["answer"] == item["answer"]
    assert r["faq"]["by"] == sample_data.FAQ_BY["글자 검색"]
    assert r["help"] == sample_data.STEP_HELP["amount"]


def test_question_without_faq_gets_step_help(client):
    r = parse(client, "holdings", "이거 어디서 봐요?")
    assert r["question"] is True and r["faq"] is None and r["help"] == sample_data.STEP_HELP["holdings"]


def test_answers_are_not_taken_as_questions(client):
    assert parse(client, "amount", "모름")["ok"] is True
    assert parse(client, "yesno", "있어요?")["ok"] is True


def test_faq_endpoint(client):
    r = client.get("/api/faq", params={"q": "배당성향이 뭐예요"}).json()
    assert r["faq"]["id"] == "payout_ratio"
    assert client.get("/api/faq", params={"q": "오늘 날씨 어때요"}).json()["faq"] is None


# --- 2026-10-30 팀 피드백 반영 ---

def test_holdings_none_or_unknown_skips_to_next_question(client):
    for word in ("없음", "모름", "몰라요"):
        r = parse(client, "holdings", word)
        assert r["ok"] is True and r["value"] == [] and r["skip"] in ("없음", "모름") and r["reply"]


def test_unknown_company_says_no_result_and_flags_it(client):
    # 목록에 없는 종목은 막지 않고 빼고 넘어가며, 그 배당은 ③에 금액으로 넣으라고 알린다
    r = parse(client, "holdings", "Z사 10주")
    assert r["ok"] and r["value"] == [] and r["excluded"] == ["Z사"] and "③" in r["note"]
    r = parse(client, "holdings", "C사 10주, Z사 5주")
    assert r["ok"] and r["value"] == [{"company": "C사", "shares": 10}] and r["excluded"] == ["Z사"]
    # 쉼표 있는 주식 수를 '3주,000주'로 쪼개 되묻지 않는다
    r = parse(client, "holdings", "C사 3,000주 · Z사 1,200주")
    assert r["ok"] and r["value"] == [{"company": "C사", "shares": 3000}] and "suggest_text" not in r
    assert data.shares_unit_added("생활·비상자금 3,000만 원 별도 보유") == "생활·비상자금 3,000만 원 별도 보유"


def test_checkup_counts_stocks_left_out_of_list(client):
    """①에서 목록에 없어 뺀 종목도 '보유 N종목'에 세고, 뺐다고 밝힌다."""
    body = {"holdings": [{"company": "C사", "shares": 3000}], "interest": 0, "other_domestic": 0, "other_foreign": 0,
            "base": 60_000_000, "outside": ["카카오"]}
    h = client.post("/api/checkup", json=body).json()["headline"]
    assert h.startswith("보유 2종목 중") and "'카카오'는 고배당기업 목록에 없어 빼고 계산했어요" in h
    r = client.post("/api/checkup", json={**body, "holdings": [], "holdings_answer": "없음"}).json()
    assert r["headline"].startswith("보유 1종목 중 0종목") and "KIND 고배당기업 목록" in r["no_target"]


def test_company_search_ignores_quotes(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(data, "companies", lambda: {"삼성전자": SimpleNamespace(stock_code="005930")})
    for q in ("삼성전자'", "'삼성전자'", "“삼성 전자”"):
        assert data.search(q) == [{"name": "삼성전자", "code": "005930"}]


def test_company_list_and_scope_guide(client):
    names = [c["name"] for c in client.get("/api/companies/list").json()]
    assert names == sorted(VIRTUAL)
    s = client.get("/api/chat/script").json()
    assert s["scope_guide"] == sample_data.SCOPE_GUIDE.format(n=len(VIRTUAL))
    assert {"없음", "모름"} <= set(s["questions"][0]["chips"])


def test_company_list_adds_preferred_after_companies(client, monkeypatch):
    from core.company_repo import RealCompany
    pref = RealCompany(**{**VIRTUAL["C사"].__dict__, "name": "C사우", "pref_of": "C사", "pref_code": "00000K"})
    monkeypatch.setattr(data, "prefs", lambda: ({"C사우": pref}, {}))
    rows = client.get("/api/companies/list").json()
    assert [r["name"] for r in rows] == [*sorted(VIRTUAL), "C사우"]
    assert rows[-1] == {"name": "C사우", "code": "00000K", "pref_of": "C사"} and not rows[0]["pref_of"]


def test_headline_names_other_income_as_reason_even_with_unknown_fields(client):
    """다른 소득이 있으면 모르는 칸이 있어도 '사업·연금·기타소득이 있어'로 이유를 말한다."""
    body = {"holdings": [{"company": "C사", "shares": 3000}], "interest": None, "other_domestic": None,
            "other_foreign": None, "base": None, "has_other_income": True}
    h = client.post("/api/checkup", json=body).json()["headline"]
    assert sample_data.HEADLINE_REASON_OTHER_INCOME in h and sample_data.HEADLINE_REASON_UNKNOWN not in h
    body["has_other_income"] = False
    assert sample_data.HEADLINE_REASON_UNKNOWN in client.post("/api/checkup", json=body).json()["headline"]


def test_shares_typed_at_other_dividend_are_not_read_as_won(client):
    """③에 '종목 + 주식 수'를 적으면 100주를 100원으로 읽지 않는다."""
    r = parse(client, "other_dividend", "C사 300주")
    assert r["ok"] is False and r["add_holdings"] == [{"company": "C사", "shares": 300}]
    r = parse(client, "other_dividend", "애플 10주", dividend_type="foreign")
    assert r["ok"] is False and r["code"] == "not_found" and sample_data.OTHER_HOLDING_OUTSIDE in r["error"]
    assert "C사 100주" in parse(client, "other_dividend", "C사")["prompt"]
    assert parse(client, "other_dividend", "국내 주식 300만 원")["value"] == {"domestic": 3_000_000, "foreign": 0}


def test_bare_word_gets_faq_answer(client):
    assert parse(client, "amount", "배당락")["faq"]["id"] == "ex_dividend"
    assert parse(client, "amount", "없음")["ok"] is True  # 답은 단어로 보지 않는다
    assert parse(client, "holdings", "C사 300주")["ok"] is True


def test_checkup_without_holdings_says_no_target(client):
    body = {"holdings": [], "holdings_answer": "모름", "interest": 5_000_000, "other_domestic": 0,
            "other_foreign": 0, "base": 60_000_000}
    r = client.post("/api/checkup", json=body).json()
    assert r["no_target"] == sample_data.NO_TARGET_REASON["모름"]
    assert r["headline"].startswith(sample_data.NO_TARGET) and r["tax"]["difference"] is None
    assert sample_data.HOLDING_ASSUMPTION not in r["notes"]  # 종목이 없으면 수량 가정 문구는 해당 없음
    assert client.post("/api/checkup", json={"holdings": []}).status_code == 422


def test_checkup_separate_only_uses_new_wording(client):
    r = client.post("/api/checkup", json={"holdings": [{"company": "C사", "shares": 3000}], "interest": None,
                                          "other_domestic": 0, "other_foreign": 0, "base": None}).json()
    labels = [k for k, _ in r["tax"]["rows"]]
    assert labels[0] == sample_data.SPECIAL_LABEL and labels[1].startswith(sample_data.SPECIAL_TAX_LABEL)
    assert "분리과세 세액" not in r["headline"] and "S(E)" not in str(r["tax"]["rows"])


JPEG = "/9j/4AAQSkZJRgABAQAAAQABAAD"  # JPEG 머리 글자(base64)


def test_holdings_image_refuses_non_photo_and_when_ai_is_off(client):
    assert client.post("/api/chat/holdings-image", json={"image": "aGVsbG8gd29ybGQ="}).json()["error"] == sample_data.IMAGE_BAD
    # 테스트에서는 Ollama가 꺼져 있다(source/tests/conftest.py)
    assert client.post("/api/chat/holdings-image", json={"image": JPEG}).json()["error"] == sample_data.IMAGE_OFF


def test_holdings_image_fills_text_for_customer_to_confirm(client, monkeypatch):
    monkeypatch.setattr(data, "get_llm", lambda: object())
    monkeypatch.setattr(data, "read_holdings_image",
                        lambda b64: [{"company": "C사", "shares": 1200}, {"company": "Z사", "shares": 5}])
    out = client.post("/api/chat/holdings-image", json={"image": "data:image/jpeg;base64," + JPEG}).json()
    assert out["ok"] and out["text"] == "C사 1,200주, Z사 5주" and out["missing"] == ["Z사"]
    assert "Z사" in out["reply"]
    # 고객이 확인해 보낸 글은 보통 답처럼 다시 읽는다
    assert parse(client, "holdings", "C사 1,200주")["value"] == [{"company": "C사", "shares": 1200}]


@pytest.mark.parametrize("items, error", [(None, sample_data.IMAGE_FAIL), ([], sample_data.IMAGE_EMPTY)])
def test_holdings_image_failure_asks_to_type(client, monkeypatch, items, error):
    monkeypatch.setattr(data, "get_llm", lambda: object())
    monkeypatch.setattr(data, "read_holdings_image", lambda b64: items)
    assert client.post("/api/chat/holdings-image", json={"image": JPEG}).json() == {"ok": False, "error": error}

def test_grid_3x3_uses_engine_boundaries():
    """3장 칸 그림: 경계는 판정 엔진과 같은 정수 비교(40%·25%·10% 정확히 그 값은 위 칸)."""
    rows = [("a", 2024, 100, None), ("a", 2025, 110, 275),   # 성향 40% 정확히, 증가 10% 정확히 → (0, 2)
            ("b", 2024, 100, None), ("b", 2025, 100, 400),   # 25% 정확히, 그대로 → (1, 1)
            ("c", 2024, 100, None), ("c", 2025, 99, 1000),   # 9.9%, 감소 → (2, 0)
            ("d", 2024, 0, None), ("d", 2025, 50, 100),      # 전년 무배당 → 빠짐
            ("e", 2024, 100, None), ("e", 2025, 120, -5)]    # 적자 → 빠짐
    g = data.grid_3x3(rows)[2025]
    assert g[0][2] == 1 and g[1][1] == 1 and g[2][0] == 1 and sum(map(sum, g)) == 3


@pytest.mark.parametrize("read, expected", [
    ({"base": 38_420_000, "gross": 52_000_000}, {"ok": True, "text": "38,420,000원", "amount": 38_420_000,
                                                 "gross": 52_000_000, "bracket": "mid"}),
    ({"base": 38_420_000, "gross": None}, {"ok": True, "text": "38,420,000원", "amount": 38_420_000}),
    ("not_page2", {"ok": False, "error": sample_data.BASE_IMAGE_NOT_PAGE2}),
    (None, {"ok": False, "error": sample_data.BASE_IMAGE_EMPTY}),
])
def test_base_image_fills_box47_amount_for_customer_to_confirm(client, monkeypatch, read, expected):
    monkeypatch.setattr(data, "get_llm", lambda: object())
    monkeypatch.setattr(data, "read_receipt_image", lambda b64: read)
    out = client.post("/api/chat/base-image", json={"image": JPEG}).json()
    assert {k: out[k] for k in expected} == expected
    if isinstance(read, dict) and read["gross"] is None:
        assert "bracket" not in out
    if out["ok"]:
        assert "㊼" in out["reply"] and parse(client, "base", out["text"])["value"] == 38_420_000


def test_base_image_refuses_non_photo(client):
    assert client.post("/api/chat/base-image", json={"image": "aGVsbG8gd29ybGQ="}).json()["error"] == sample_data.IMAGE_BAD


def test_analysis_macro_reads_saved_results():
    _db_or_skip()
    m = data.analysis()["macro"]
    if m is None:
        pytest.skip("거시지표 상관 결과가 아직 없음 (scripts.analyze_macro_dividend)")
    assert {c[0] for c in m["corr"]} == {k for k, _ in m["lags"]}
    assert all(len(r) == len(m["year_cols"]) + 1 for r in m["years"])
    assert all(c[3] in m["macro_names"] for c in m["corr"])


def test_isa_irp_guide(client):
    r = client.get("/api/isa-irp", params={"bracket": "low", "profit": 3_000_000, "irp": 9_000_000}).json()
    assert r["chosen"]["isa_type"] == "서민형" and r["isa"]["low_income"] == 0 and r["irp"][0]["credit"] == 1_485_000
    assert client.get("/api/isa-irp", params={"bracket": "x"}).status_code == 422


def test_analysis_behavior_reads_saved_results():
    _db_or_skip()
    b = data.analysis()["behavior"]
    if b is None:
        pytest.skip("회사 행동 분석 결과가 아직 없음 (scripts.analyze_exposure_dividend · analyze_policy_did)")
    for key in ("exposure", "policy"):
        prim = [f for f in b["fits"][key] if f["role"] == "primary"]
        assert len(prim) == 2 and all(f["p_holm"] is not None for f in prim)
    years = [r[1] for r in b["series"]["policy"]["es_holder"]]
    assert years == sorted(years) and 2025 in years


def test_docs_chip_points_to_official_issuers(client):
    s = client.get("/api/chat/script").json()
    assert s["docs_chip"] in s["addon_chips"]
    urls = {link["url"] for item in s["docs_guide"]["items"] for link in item["links"]}
    assert urls <= {"https://www.hometax.go.kr", "https://www.gov.kr"} and "https://www.hometax.go.kr" in urls


def test_english_layout_input_is_read_as_hangul(client):
    r = client.post("/api/chat/parse", json={"kind": "holdings", "text": "samsung 10주"}).json()  # 한글 글자가 안 되는 영문은 그대로
    # 'samsung'은 한글 자판 글이 아니라 바꾸지 않고, 별칭 표로 '삼성전자'인지 되묻는다
    assert "fixed_text" not in r and r["suggest_text"] == "삼성전자 10주"
    r = client.post("/api/chat/parse", json={"kind": "holdings", "text": "C사 10wn"}).json()  # '10wn' → '10주'
    assert r["ok"] and r["fixed_text"] == "C사 10주"
    r = client.post("/api/chat/parse", json={"kind": "holdings", "text": "tlqkf"}).json()
    assert r["guard"] == "거친 말" and r["fixed_text"] == "시발"
    r = client.post("/api/chat/parse", json={"kind": "amount", "text": "50aksdnjs"}).json()  # 규칙만으로 읽히는 경우(시험은 AI를 끔)
    assert r["ok"] and r["value"] == 500_000 and r["fixed_text"] == "50만원"


def test_alias_table_asks_back_instead_of_computing(client, monkeypatch):
    from core import company_alias
    monkeypatch.setattr(company_alias, "load", lambda path=None: (company_alias.Alias("가나상사", "C사", "옛 이름"),))
    r = client.post("/api/chat/parse", json={"kind": "holdings", "text": "가나상사 10주"}).json()
    assert r["ok"] is False and r["suggest_text"] == "C사 10주" and "지금 이름이 'C사'예요" in r["reply"]
    assert client.post("/api/chat/parse", json={"kind": "holdings", "text": "C사 10주"}).json()["ok"]


def test_bare_number_holdings_asks_back(client):
    r = client.post("/api/chat/parse", json={"kind": "holdings", "text": "C사 10"}).json()
    assert r["ok"] is False and r["suggest_text"] == "C사 10주"
    r = client.post("/api/chat/parse", json={"kind": "holdings", "text": "C사: 10, 없는회사: 3"}).json()
    assert r["ok"] is False and r["suggest_text"] == "C사 10주, 없는회사 3주"
    r = client.post("/api/chat/parse", json={"kind": "holdings", "text": r["suggest_text"]}).json()
    assert r["ok"] and r["excluded"] == ["없는회사"]


def test_no_stock_phrases_skip(client):
    for t in ("주식 없음", "보유 주식은 없어요"):
        r = client.post("/api/chat/parse", json={"kind": "holdings", "text": t}).json()
        assert r["ok"] and r["value"] == [] and r["skip"] == "없음"


def test_other_dividend_split_foreign_and_domestic(client):
    r = client.post("/api/chat/parse", json={"kind": "other_dividend", "text": "미국 주식 50만원 국내 30만원"}).json()
    assert r["ok"] and r["value"] == {"domestic": 300_000, "foreign": 500_000}
    r = client.post("/api/chat/parse", json={"kind": "other_dividend", "text": "미국 주식 50만원"}).json()
    assert r["value"] == {"domestic": 0, "foreign": 500_000}


def test_base_small_number_and_monthly_ask_back(client):
    r = client.post("/api/chat/parse", json={"kind": "base", "text": "연봉 5000"}).json()
    assert r["ok"] is False and r["suggest_text"] == "5,000만 원"
    r = client.post("/api/chat/parse", json={"kind": "base", "text": "월급 300"}).json()
    assert r["ok"] is False and r["suggest_text"] == "3,600만 원" and "× 12" in r["reply"]
    assert client.post("/api/chat/parse", json={"kind": "base", "text": "5,000만 원"}).json()["value"] == 50_000_000


def test_trust_totals_count_source_and_result_rows_separately():
    _db_or_skip()
    t = data.analysis()["trust"]["totals"]
    if t is None:
        pytest.skip("대조군 표가 없음")
    assert t["source_rows"] > t["price_rows"] > 0 and t["result_rows"] > 0
    assert t["source_tables"] > 0 and t["result_tables"] > 0


def test_persona_pages():
    _db_or_skip()
    c = TestClient(main.app)
    assert [p["id"] for p in c.get("/api/personas").json()] == ["kim", "go"]
    kim = c.get("/api/personas/kim").json()
    # 페르소나 문서의 숫자를 엔진이 그대로 재현하는지 (특례배당 2,462만 원, 세액 차이 817,700원 감소)
    assert kim["financial_total"] == 33_620_000 and kim["withheld_after"] == 28_442_520
    assert kim["checkup"]["special_total"] == 24_620_000
    assert kim["checkup"]["tax"]["difference"] == 817_700 and kim["checkup"]["tax"]["direction"] == "감소"
    go = c.get("/api/personas/go").json()
    assert go["financial_total"] == 480_000 and go["isa_irp"]["isa"]["type"] == "서민형"
    assert c.get("/api/personas/nobody").status_code == 404


def test_entry_negative_shares_is_answered_not_sent_to_term_help(client):
    """시작 단계 '-10주': 바로 쓸 수 있는 되묻기 답(bad_shares)을 돌려줘, 화면이 용어 사전 안내로 넘기지 않게 한다."""
    r = client.post("/api/chat/parse", json={"kind": "holdings", "text": "C사 -10주"}).json()
    assert r["code"] == "bad_shares" and "몇 주 가지고 계신가요" in r["error"]


# 점검 답도 질문도 아닌 말 → 용어 사전 안내 대신 뜻에 맞는 정해 둔 답 (화면 캡처 '야야', '야야!@#!')
CASUAL = {
    "거친 말": ["야야!@#!", "!@#", "#$%", "ㅗ", "바보", "멍청이"],
    "부르기": ["야", "야야", "저기요", "여보세요", "모아야", "이봐"],
    "잡음": ["ㅋㅋㅋ", "ㅎㅎ", "ㅠㅠ", "...", "???", "ㅁㄴㅇㄹ", "!!!"],
    "불만": ["답답해", "짜증나", "못 알아듣네", "왜 이래", "장난해?", "이거 뭐야", "헐", "에휴"],
}


@pytest.mark.parametrize("kind", ["holdings", "amount", "other_dividend", "yesno", "base"])
def test_casual_words_get_fixed_reply_at_every_step(client, kind):
    for group, words in CASUAL.items():
        for w in words:
            r = parse(client, kind, w)
            if group == "거친 말":
                assert r.get("guard") == "거친 말", (kind, w, r)
            else:
                assert r.get("chat") and not r.get("ok"), (kind, w, r)


# 새 규칙이 단계별 진짜 답을 먹지 않는지: 답이 그대로 값으로 읽혀야 한다
ANSWERS = {
    "holdings": [("C사 300주", [{"company": "C사", "shares": 300}]), ("C사 삼백 주", [{"company": "C사", "shares": 300}])],
    "amount": [("500만", 5_000_000), ("없음", 0), ("모름", None), ("3천만 원!", 30_000_000)],
    "yesno": [("ㅇㅇ", True), ("ㄴㄴ", False), ("응", True), ("아니", False), ("ㅇ", True), ("ㄴ", False), ("있어요", True), ("없어!", False)],
    "base": [("4000만", 40_000_000), ("근로소득 없음", 0), ("모름", None)],
}


@pytest.mark.parametrize("kind", list(ANSWERS))
def test_real_answers_are_not_swallowed_by_casual_rules(client, kind):
    for text_, value in ANSWERS[kind]:
        r = parse(client, kind, text_)
        assert r.get("ok") and r["value"] == value, (kind, text_, r)


def test_bare_number_at_holdings_asks_for_the_name(client):
    for t in ("1", "300", "1,000"):
        r = parse(client, "holdings", t)
        assert r["code"] == "missing_name" and "종목 이름" in r["error"]
    assert parse(client, "amount", "300")["ok"]  # 금액 단계에서는 그대로 금액


def test_casual_rules_never_catch_a_company_name(client):
    from core import chat_guard
    for name in data.name_index():
        assert not (chat_guard.check(name) or chat_guard.casual(name) or chat_guard.small_talk(name)), name


def test_script_has_start_step_words_and_two_fallbacks(client):
    s = client.get("/api/chat/script").json()
    assert s["entry_unclear"] != s["entry_fallback"]
    assert {"start", "decline", "help"} <= set(s["entry_words"]) and set(s["entry_replies"]) == {"decline", "help"}
    for words in s["entry_words"].values():  # 화면이 띄어쓰기·끝 문장부호를 지우고 맞추므로 목록도 그 모양이어야 한다
        assert all(w == w.replace(" ", "").lower().rstrip(".!~?") for w in words)


def test_script_has_ai_notice_mark_and_receipt_guide(client):
    """인공지능기본법 제31조 사전 고지·'AI가 읽은 값' 표시·영수증 칸 안내가 화면 문구에 그대로 내려온다."""
    from core import sample_data as text
    s = client.get("/api/chat/script").json()
    assert s["ai_note"] == text.WEB_ADDON_NOTE
    for part in ("AI를 사용합니다", "사진 읽기", "외부로 보내지 않습니다", "참고용"):
        assert part in s["ai_note"]
    assert s["ai_read_mark"] == "AI가 읽은 값"
    assert "㊼" in s["receipt_guide"] and "2쪽" in s["receipt_guide"] and "㉑" in s["receipt_guide"]


def test_term_dictionary_answers_exact_terms_only(client):
    """금융위원회 금융용어사전·원픽 보충 용어: 이름이 정확히 맞을 때만 그 항목 그대로(생성 없음), 가드의 '매도'보다 먼저."""
    from core import term_dict
    if not term_dict.FSC.exists():
        pytest.skip("금융위원회 사전 파일 없음 (scripts.collect_fsc_glossary)")
    r = parse(client, "holdings", "공매도란?")
    assert r["question"] and r["faq"]["title"] == "공매도" and r["faq"]["source_label"] == "금융위원회 금융용어사전"
    assert r["faq"]["source_url"].startswith("https://www.fsc.go.kr/in090301/view?dicId=")
    assert parse(client, "holdings", "IPO가 뭐야")["faq"]["title"].startswith("IPO")
    assert parse(client, "holdings", "기업공개")["faq"]["title"].startswith("IPO")  # 괄호 안 이름도 별칭
    assert not parse(client, "holdings", "공매도 해도 돼?").get("faq")  # 판단 질문은 그대로 가드로
    assert parse(client, "holdings", "공매도 해도 돼?").get("guard")


def test_term_dictionary_never_takes_real_answers(client):
    from core import term_dict
    for name in data.name_index():  # 회사 이름이 사전 용어로 읽히면 종목 답이 막힌다
        assert term_dict.find(name) is None, name
    for kind, answers in ANSWERS.items():
        for text_, value in answers:
            r = parse(client, kind, text_)
            assert r.get("ok") and r["value"] == value, (kind, text_, r)


def test_team_answers_win_over_dictionary_for_same_term(client):
    r = parse(client, "holdings", "ETF 뜻")
    assert not r["faq"]["id"].startswith("term-")


def test_onepick_terms_each_have_a_checked_source():
    """원픽 보충 용어: 항목마다 연 출처 주소·출처 종류가 있고, 풀이 길이가 정해진 범위 안."""
    import json
    from core import term_dict
    data_ = json.loads(term_dict.ONEPICK.read_text(encoding="utf-8"))
    assert data_["terms"]
    for t in data_["terms"]:
        assert t["source_url"].startswith("http") and t["source_name"] and t["source_type"] in ("공공기관", "민간 해설(기관 자료 없음)"), t
        assert 60 <= len(t["definition"]) <= 260, t["term"]


def test_terms_list_for_glossary_tab(client):
    from core import term_dict
    if not term_dict.FSC.exists():
        pytest.skip("금융위원회 사전 파일 없음")
    r = client.get("/api/terms").json()
    kinds = {t["kind"] for t in r["terms"]}
    assert kinds == {"fsc", "onepick"} and set(r["notice"]) == kinds
    assert len(r["terms"]) == sum(term_dict.counts().values())  # 별칭으로 겹친 항목은 한 번만
    assert all(t["source_url"].startswith("http") and t["definition"] for t in r["terms"])
