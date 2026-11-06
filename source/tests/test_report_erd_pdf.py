"""DB 전체 ERD: 모든 표·보기가 빠짐없이 들어가고, 연결 비율을 실제로 센다."""
import pytest

from scripts import report_erd_pdf as erd


@pytest.fixture(scope="module")
def loaded():
    try:
        return erd.load()
    except Exception:  # noqa: BLE001
        pytest.skip("PostgreSQL에 연결할 수 없음")


def test_every_table_and_view_is_drawn(loaded):
    tables, links = loaded
    html = erd.build(tables, links)
    for name, t in tables.items():
        assert f"<div class='card {t.schema}" in html and escape_name(name) in html


def escape_name(name: str) -> str:
    return f">{name}<span>"


def test_links_are_counted(loaded):
    _, links = loaded
    assert any(l["kind"] == "외래키" for l in links)
    for l in links:
        assert 0 <= l["hit"] <= l["total"]
    # 판정 결과는 모두 회사 표에 이어져야 한다
    judge = next(l for l in links if l["from"] == "core.core_judgement_2026")
    assert judge["hit"] == judge["total"] > 0
