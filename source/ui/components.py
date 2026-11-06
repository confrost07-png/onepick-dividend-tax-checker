"""여러 화면에서 함께 쓰는 부품. *_html 함수는 HTML 문자열만 만든다."""
from html import escape

# 피그마 '결과 꼬리표' 컴포넌트의 종류 4가지
TAG_KINDS = {
    "공시 사실": "fact",
    "확인 완료 계산": "calc",
    "현재 해석 기준": "interp",
    "판정 보류": "hold",
    "임시 데이터": "interp",
}


def won(amount: int) -> str:
    """원 단위 금액 표시. 1억 원 이상은 억 원(소수 첫째 자리), 그 아래는 원 단위 그대로."""
    if abs(amount) >= 100_000_000:
        return f"{amount / 100_000_000:,.1f}억 원".replace(".0억", "억")
    return f"{amount:,}원"


def tag_html(kind: str) -> str:
    if kind not in TAG_KINDS:
        raise ValueError(f"알 수 없는 꼬리표 종류: {kind}")
    return f'<span class="op-tag op-tag--{TAG_KINDS[kind]}">{escape(kind)}</span>'


def badge_html(text: str, ok: bool) -> str:
    tone = "ok" if ok else "bad"
    return f'<span class="op-tag op-tag--{tone}">{escape(text)}</span>'


def header_html(title: str, lead: str, tag: str | None = None, small: bool = False) -> str:
    """화면 머리: 제목(옆에 꼬리표) 아래 부제. small은 챗봇 화면(제목 26px, 부제 13px)."""
    badge = f'<span class="op-tag op-tag--lg op-tag--interp">{escape(tag)}</span>' if tag else ""
    size = " op-header--sm" if small else ""
    return (f'<div class="op-header{size}"><div class="op-header__row">'
            f'<h1 class="op-header__title">{escape(title)}</h1>{badge}</div>'
            f'<p class="op-header__lead">{escape(lead)}</p></div>')


def axis_html(days: int) -> str:
    """차트 아래 축 안내 줄: 공시일(0) · 공시 후 거래일 → · N"""
    return f'<div class="op-axis"><span>공시일(0)</span><span>공시 후 거래일 →</span><span>{days}</span></div>'


def notice_html(text: str) -> str:
    return f'<div class="op-notice">{escape(text)}</div>'


def metric_html(label: str, value: str, caption: str, small: bool = False) -> str:
    size = " op-metric--sm" if small else ""
    return (
        f'<div class="op-metric{size}">'
        f'<p class="op-metric__label">{escape(label)}</p>'
        f'<p class="op-metric__value">{escape(value)}</p>'
        f'<p class="op-metric__caption">{escape(caption)}</p>'
        "</div>"
    )


def table_html(headers: list[str], rows: list[list[str]], num_cols: set[int], plain: bool = False) -> str:
    """num_cols에 든 열 번호는 오른쪽 정렬한다. 셀 값은 escape 하므로 HTML을 넣으려면 cell_html을 쓴다."""
    def cell(tag: str, i: int, value) -> str:
        cls = ' class="num"' if i in num_cols else ""
        body = value.html if isinstance(value, Raw) else escape(str(value))
        return f"<{tag}{cls}>{body}</{tag}>"

    head = "".join(cell("th", i, h) for i, h in enumerate(headers))
    body = "".join("<tr>" + "".join(cell("td", i, v) for i, v in enumerate(r)) + "</tr>" for r in rows)
    cls = "op-table op-table--plain" if plain else "op-table"
    return f'<table class="{cls}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


class Raw:
    """이미 안전하게 만든 HTML 조각(꼬리표·배지)을 표나 목록에 그대로 넣을 때 쓴다."""

    def __init__(self, html: str):
        self.html = html


def kv_html(rows: list[tuple]) -> str:
    """(라벨, 값) 또는 (라벨, 값, 꼬리표) 목록을 두 열 목록으로 만든다. 꼬리표는 종류 이름이나 Raw."""
    parts = []
    for row in rows:
        label, value = row[0], row[1]
        extra = row[2] if len(row) > 2 else None
        tag = f" {extra.html if isinstance(extra, Raw) else tag_html(extra)}" if extra else ""
        parts.append(f"<dt>{escape(label)}</dt><dd>{escape(value)}{tag}</dd>")
    return f'<dl class="op-kv">{"".join(parts)}</dl>'

