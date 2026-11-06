"""한/영 전환을 잊고 친 글을 한글로 되돌리기 (core.keyboard)."""
from core.keyboard import fix_layout, to_hangul


def test_qwerty_typed_korean_is_restored():
    assert fix_layout("tkatjdwjswk 10wn") == "삼성전자 10주"
    assert fix_layout("dnflrmadbdwlwn 300wn") == "우리금융지주 300주"
    assert fix_layout("qoekdfkrdlfks?") == "배당락이란?"
    assert fix_layout("dhtlqakS dnjs") == "오십만 원"


def test_meaningful_english_is_kept():
    assert fix_layout("samsung 10") is None  # 한글 글자가 되지 않으면 그대로
    assert fix_layout("ETF란?") is None
    assert fix_layout("KB금융 10주", {"kb"}) is None
    assert to_hangul("hi") is None
