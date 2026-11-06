"""자주 틀리는 회사 이름 표(data/processed/chat/company_alias.csv): 바꾼 글로 되묻기만 하고 바로 계산하지 않는다."""
import pytest

from core import company_alias as ca
from core.company_alias import Alias


def test_table_rows_are_well_formed():
    rows = ca.load()
    assert len(rows) >= 50
    assert all(a.written and a.company and a.kind for a in rows)
    assert len({a.written.lower() for a in rows}) == len(rows)  # 같은 입력이 두 번 없음


def test_every_target_is_a_listed_company_and_no_alias_is_a_real_name():
    """표의 대상 기업은 모두 638곳 안에 있고, 별칭이 실제 대상 기업 이름과 같지 않다(DB가 있어야 함)."""
    data = pytest.importorskip("api.data")
    try:
        index = data.name_index()
    except Exception:
        pytest.skip("DB 없음")
    names = set(index.values())
    assert [a.company for a in ca.load() if a.company not in names] == []
    assert [a.written for a in ca.load() if a.written in index] == []


def test_replace_whole_names_only():
    assert ca.replace("삼전 10주")[0] == "삼성전자 10주"
    assert ca.replace("국민은행 50주, 신한은행 30주")[0] == "KB금융 50주, 신한지주 30주"
    assert ca.replace("lg cns 2주")[0] == "LG씨엔에스 2주"
    assert ca.replace("삼성화재해상보험 5주")[1] == []  # 이미 맞는 이름 안의 줄임말은 건드리지 않음
    assert ca.replace("포스코인터내셔널 3주")[1] == []


def test_ask_text_explains_subsidiary_and_old_name():
    t = ca.ask_text([Alias("국민은행", "KB금융", "자회사"), Alias("롯데제과", "롯데웰푸드", "옛 이름")])
    assert t.startswith("'국민은행'은 따로 상장되지 않았어요. 지주회사인 'KB금융' 말씀인가요?")
    assert "'롯데제과'는 지금 이름이 '롯데웰푸드'예요." in t and "[보내기]" in t
    assert "'현대중공업'은 지금 이름이 'HD현대중공업'이에요." in ca.ask_text([Alias("현대중공업", "HD현대중공업", "옛 이름")])
    assert [a.written for a in ca.replace("삼전 10주, 국민은행 50주")[1]] == ["삼전", "국민은행"]  # 적힌 순서
