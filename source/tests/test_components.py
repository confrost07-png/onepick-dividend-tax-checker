"""API가 쓰는 화면 조각(source/ui/components.py) 테스트: 꼬리표·표·금액 표시."""
import pytest

from core import sample_data as data
from ui.components import Raw, badge_html, kv_html, metric_html, notice_html, table_html, tag_html


def test_tag_kinds_match_figma():
    assert 'op-tag--fact">공시 사실' in tag_html("공시 사실")
    assert 'op-tag--hold">판정 보류' in tag_html("판정 보류")
    with pytest.raises(ValueError):
        tag_html("없는 종류")


def test_badge_tone():
    assert "op-tag--ok" in badge_html("통과", True)
    assert "op-tag--bad" in badge_html("미충족", False)


def test_text_is_escaped():
    assert "&lt;b&gt;" in notice_html("<b>")
    assert "&lt;b&gt;" in metric_html("<b>", "1", "c")


def test_table_right_aligns_number_columns_only():
    html = table_html(["이름", "값"], [["가", "1"]], num_cols={1})
    assert "<td>가</td>" in html
    assert '<td class="num">1</td>' in html
    assert '<th class="num">값</th>' in html


def test_table_keeps_raw_html():
    html = table_html(["결과"], [[Raw(badge_html("통과", True))]], num_cols=set())
    assert "<span" in html


def test_kv_adds_tag_when_given():
    html = kv_html([("라벨", "값", "공시 사실"), ("라벨2", "값2")])
    assert html.count('class="op-tag ') == 1


def test_example_curve_shape():
    for days in data.WINDOWS.values():
        df = data.example_curve(days)
        assert len(df) == days + 1
        assert (df["q25"] <= df["median"]).all() and (df["median"] <= df["q75"]).all()
