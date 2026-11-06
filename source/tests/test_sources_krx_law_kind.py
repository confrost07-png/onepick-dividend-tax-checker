"""KRX 시세·법령 원문·KIND 목록의 결측 구분(가짜 응답, 인터넷 없이)."""
import json

import pandas as pd
import pytest

from core.event_study import car
from core.sources import samples
from core.sources.base import API_ERROR, OK, STORED, UNVERIFIED, Client
from core.sources.kind import attach_corp_codes, load_kind_list
from core.sources.krx import (
    AFTER_LAST_TRADE,
    BEFORE_LISTING,
    HALTED,
    NORMAL,
    classify_days,
    fetch_ohlcv,
    normalize_ticker,
    price_panel,
)
from core.sources.law import Law, parse_article_label, stored_article
from core.sources.opendart import Dart

# --- KRX ---


@pytest.mark.parametrize("raw", [12345, "12345", "A012345", "012345.KS"])
def test_normalize_ticker(raw):
    assert normalize_ticker(raw) == "012345"


def test_halted_and_before_listing_are_not_prices():
    p = samples.FakePrices()
    panel = price_panel(["12345", "067890"], "2026-01-02", "2026-01-09", provider=p,
                        key_map={"012345": samples.CORP})
    prices = panel["prices"]
    assert prices[samples.CORP].isna().tolist() == [False, False, True, True, False, False]
    assert prices["067890"].isna().sum() == 4
    report = panel["report"].set_index("종목코드")
    assert report.loc["012345", HALTED] == 2
    assert report.loc["067890", BEFORE_LISTING] == 4
    # 거래정지일이 관측 기간에 들어가면 CAR을 계산하지 않는다(값을 채우지 않음)
    assert car(prices[samples.CORP], panel["market"], 1, 2) is None
    assert car(prices[samples.CORP], panel["market"], 1, 0) is not None  # 정지 전 구간은 계산됨


def test_after_last_trade():
    days = pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"])
    df = pd.DataFrame({"시가": [1, 1], "종가": [1, 1], "거래량": [1, 1]}, index=days[:2])
    assert classify_days(df, days)["상태"].tolist() == [NORMAL, NORMAL, AFTER_LAST_TRADE]


def test_fallback_provider_used_when_first_fails():
    class Broken:
        name = "고장"

        def prices(self, *a):
            raise ConnectionError("KRX 차단")

    got = fetch_ohlcv("012345", "2026-01-02", "2026-01-09", provider=Broken(), fallback=samples.FakePrices())
    assert got.status == OK and got.source.api == "가짜 시세"
    assert got.attempts[0].startswith("고장 012345: 조회 실패")


def test_empty_index_is_api_error():
    class Empty(samples.FakePrices):
        def index(self, *a):
            return pd.DataFrame()

    with pytest.raises(RuntimeError, match="거래일 달력"):
        price_panel(["012345"], "2026-01-02", "2026-01-09", provider=Empty())


# --- 법령 ---


def test_parse_article_label():
    assert parse_article_label("제104조의27") == ("104", "27")
    assert parse_article_label(104) == ("104", "")


def test_law_article_handles_single_dicts_and_nested_text():
    law = Law(oc="test", client=Client(fetch=samples.fake_law_fetch))
    got = law.article("조세특례제한법", "제104조의27")
    assert got.status == OK
    assert got.value["title"] == "고배당기업 주식 배당소득에 대한 과세특례"
    text = got.value["text"]
    assert "① 다음 각 호의" in text and "2. 가상 요건 둘" in text and "가. 가상 세부 요건" in text


def test_law_falls_back_to_stored_copy(tmp_path):
    stored = tmp_path / "articles.json"
    stored.write_text(json.dumps({"fetched": "2026-10-22", "passages": [
        {"law": "조세특례제한법", "article": "제104조의27(고배당기업)", "paragraph": "①", "text": "① 보관본 원문",
         "url": "https://www.law.go.kr/x", "effective": "2026. 9. 18."}]}, ensure_ascii=False), encoding="utf-8")
    law = Law(oc="wrong", client=Client(fetch=samples.fake_law_fetch), stored_path=stored)
    got = law.article("조세특례제한법", "제104조의27")
    assert got.status == STORED and got.value["text"] == "① 보관본 원문"
    assert got.attempts[0].startswith("lawSearch: JSON이 아닌 응답")
    assert stored_article("조세특례제한법", "1", path=stored).status == UNVERIFIED


# --- KIND ---


def test_kind_html_disguised_as_xls_keeps_leading_zero_and_flags_year(tmp_path):
    f = tmp_path / "kind.xls"
    f.write_text(
        "<table><tr><th>종목명</th><th>종목코드</th><th>사업연도</th><th>결산월</th><th>배당성향(%)</th></tr>"
        "<tr><td>가나다</td><td>12345</td><td>2025</td><td>12</td><td>45.1</td></tr>"
        "<tr><td>이상한회사</td><td>067890</td><td>2026</td><td>12</td><td>359.84</td></tr>"
        "<tr><td>없는회사</td><td></td><td>2025</td><td>12</td><td>-</td></tr></table>", encoding="utf-8")
    df, issues = load_kind_list(f, expected_year=2025)
    assert df["종목코드"].tolist()[:2] == ["012345", "067890"]
    memo = " / ".join(issues["점검"])
    assert "12월 결산인데 연도가 다름" in memo and "종목코드 비어 있음" in memo and "배당성향 값 없음" in memo

    corp = Dart(key="k", client=Client(fetch=samples.fake_dart_fetch)).corp_codes()
    mapped = attach_corp_codes(df, corp)
    assert mapped["corp_code"].tolist()[:2] == [samples.CORP, "00000002"]
    assert mapped["매핑 상태"].tolist()[2] == UNVERIFIED


def test_kind_missing_required_column(tmp_path):
    f = tmp_path / "bad.csv"
    f.write_text("이름,값\n가,1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="필수 열"):
        load_kind_list(f)



# --- KIND · DART 매핑표 ---

from core.sources.kind import build_company_map  # noqa: E402
from core.sources.krx import listing, market_panels  # noqa: E402


@pytest.fixture
def kind_file(tmp_path):
    f = tmp_path / "밸류업고배당기업.xls"
    f.write_bytes(samples.KIND_HTML.encode("cp949"))  # 실제 파일처럼 cp949
    return f


def test_kind_file_without_stock_code_column(kind_file):
    df, issues = load_kind_list(kind_file, expected_year=2025)
    assert len(df) == 7 and "종목코드" not in df
    assert set(df.columns) >= {"회사명", "시장구분", "사업연도", "결산월", "배당성향", "이익배당금증가율", "공시제목"}
    assert "배당성향 값 없음" in " ".join(issues["점검"])


def test_company_map_by_name_short_name_and_market(kind_file):
    df, _ = load_kind_list(kind_file, expected_year=2025)
    dart = Dart(key="k", client=Client(fetch=samples.fake_dart_fetch))
    m, check = build_company_map(df, dart.corp_codes(), dart, expected_year=2025)
    got = m.set_index("회사명")
    # 줄임말: 앞부분이 같은 '인지디스플레이테크'(유가)는 시장이 달라 빠짐
    assert got.loc["인지디스플레", "corp_code"] == "00000004"
    assert got.loc["인지디스플레", "매핑 방법"] == "회사명 앞부분 일치(줄임말)"
    # 정식 이름이 전혀 다른 경우: DART 종목명(약칭)으로 찾음
    assert got.loc["현대차", "corp_code"] == "00000005" and got.loc["현대차", "매핑 방법"] == "DART 종목명(약칭) 일치"
    assert got.loc["GS", "corp_code"] == "00000006"  # GS리테일이 아님
    assert "금융업" in got.loc["신영증권", "점검"] and "03월 결산" in got.loc["신영증권", "점검"]
    assert "사업연도 2026" in got.loc["신영증권", "점검"]
    assert got.loc["없는회사", "매핑 상태"] == UNVERIFIED and pd.isna(got.loc["없는회사", "corp_code"])
    assert set(check["회사명"]) >= {"인지디스플레", "현대차", "신영증권", "없는회사"}
    assert m["corp_code"].dropna().is_unique


def test_listing_and_market_panels():
    p = samples.FakePrices()
    lst = listing("2026-01-09", provider=p)
    assert lst.status == OK and set(lst.value["시장"]) == {"KOSPI", "KOSDAQ"}
    out = market_panels({"KOSDAQ": ["012345"], "KOSPI": ["067890"]}, "2026-01-02", "2026-01-09", provider=p)
    assert out["market_of"] == {"012345": "KOSDAQ", "067890": "KOSPI"}
    assert set(out["markets"]) == {"KOSDAQ", "KOSPI"} and list(out["prices"].columns) == ["012345", "067890"]
