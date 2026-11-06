"""onepick DB 전체 ERD PDF → report/설계/DB_ERD_전체.pdf

실행: .venv/bin/python -m scripts.report_erd_pdf [--out ...] [--html-only]
- 표·보기·열·기본키·외래키·설명은 지금 DB(information_schema, pg_catalog)에서 읽는다. 손으로 적은 구조는 없다.
- 연결은 두 가지로 그린다: 선언된 외래키(실선)와 같은 키로 잇는 논리 연결(점선, corp_code·rcept_no).
  논리 연결은 만들 때마다 실제로 이어지는 값의 비율을 세어 적는다(독자가 같은 SQL로 다시 셀 수 있게).
- 원픽 디자인 토큰(source/scripts/report_story_pdf.py와 같음). A4 가로, macOS WebKit 인쇄(source/scripts/html_to_pdf.swift).
"""
import argparse
import shutil
import subprocess
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from html import escape
from pathlib import Path

from core import db
from scripts.report_story_pdf import COIN, COIN_DEEP, GRAY, INK, LINE, OK, PAPER, SEA, SEA_DEEP, WAVE

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "report" / "설계" / "DB_ERD_전체.pdf"
SCHEMAS = ("raw", "ref", "core", "partner")

# 영역: 상세 ERD 한 장에 함께 그릴 표·보기. 여기 없는 표는 '그 밖'으로 간다(새 표가 생겨도 빠지지 않게)
DOMAINS = [
    ("판정·배당", "고배당기업 638곳의 배당·재무 원천과, 요건 판정·최소 필요 배당·재무 여력 결과",
     ["core.core_company", "raw.kind_list", "raw.dart_dividend_item", "raw.dart_financial", "raw.dividend_decision", "raw.cf_dividend_paid",
      "raw.cf_dividend_account", "core.core_dividend_year", "core.core_financial_year", "core.v_dividend_year_filled", "core.v_financial_year_filled",
      "core.v_dividend_year_verified", "core.v_financial_year_verified", "core.core_judgement_2026", "core.core_min_dividend_2027",
      "core.core_capacity_2025", "ref.tax_rate"]),
    ("원문 검증", "DB 숫자를 공시 원문과 다시 맞춰 본 결과, 팀 검토 확정 값, 빈칸 채움, 주식 수 점검",
     ["core.core_source_verify", "core.core_dart_verify", "core.core_review_value", "core.core_dart_fill", "core.core_setting", "core.v_dart_mismatch",
      "raw.dart_share_total", "core.core_share_check", "core.v_share_total_checked"]),
    ("주가·공시 반응", "KRX 주가·지수와 날짜별 사용 등급, 배당·자본 변동 공시 뒤 초과수익률",
     ["raw.krx_price_daily", "raw.krx_day_status", "raw.krx_market_index", "core.core_price_flag", "core.core_index_flag", "core.v_price_daily",
      "core.v_index_daily", "core.v_price_coverage", "raw.dart_filing_list", "raw.dart_capital_event", "raw.dart_split_merge", "raw.dart_capital_fetch_log",
      "core.v_split_merge_with_reduction", "core.core_event_car", "core.core_event_curve", "core.core_event_summary"]),
    ("밸류업 정책", "기업가치 제고 계획 공시 원문·OCR·검색 조각과 팀이 분류한 약속",
     ["raw.policy_filing", "raw.policy_document", "raw.policy_chunk", "raw.policy_page_ocr", "core.v_policy_filing_latest", "raw.dart_policy_filing",
      "core.v_policy_filing", "core.core_policy_item", "core.core_demo_company"]),
    ("최대주주·경기·행동", "최대주주 지분, 한국은행 경기 지표와 배당 상관, 노출도·제도 효과 회귀 결과",
     ["raw.dart_major_holder", "core.core_major_holder", "raw.ecos_macro", "core.core_macro_dividend_year", "core.core_macro_dividend_corr",
      "core.core_behavior_fit", "core.core_behavior_series"]),
    ("대조군 (partner)", "같은 4개 업종 상장사 대조군 데이터와, 우리 값과 합친 패널",
     ["partner.company", "partner.report", "partner.filing", "partner.financial_year", "partner.dividend_year", "partner.dividend_item", "partner.fs_line",
      "partner.share_total", "partner.major_holder", "partner.audit_opinion", "partner.risk_event", "partner.krx_price_daily", "partner.v_panel",
      "partner.analysis_result"]),
]

# corp_code 말고 따로 잇는 논리 연결: (표, 열, [(대상 표, 대상 열)…], 설명). 대상이 여럿이면 어느 하나에 있으면 이어진 것으로 센다
EXTRA_LINKS = [
    ("core.core_policy_item", "rcept_no", [("raw.policy_filing", "rcept_no")], "팀이 분류한 약속 → 그 공시"),
    ("core.core_event_car", "rcept_no", [("raw.dart_filing_list", "rcept_no")], "공시 뒤 초과수익률 → 그 공시(OpenDART 공시 목록)"),
    ("raw.dividend_decision", "rcept_no", [("raw.dart_filing_list", "rcept_no")], "배당 결정 공시 → OpenDART 공시 목록"),
    ("raw.dart_capital_event", "rcept_no", [("raw.dart_filing_list", "rcept_no")], "증자·감자 공시 → OpenDART 공시 목록"),
    ("partner.fs_line", "rcept_no", [("partner.report", "rcept_no")], "재무제표 줄 → 그 사업보고서"),
    ("partner.dividend_item", "rcept_no", [("partner.report", "rcept_no")], "배당 표 칸 → 그 사업보고서"),
    ("partner.major_holder", "rcept_no", [("partner.report", "rcept_no")], "최대주주 줄 → 그 사업보고서"),
    ("partner.share_total", "rcept_no", [("partner.report", "rcept_no")], "주식 총수 줄 → 그 사업보고서"),
]
HUB = {"partner": ("partner.company", "corp_code")}
DEFAULT_HUB = ("core.core_company", "corp_code")


@dataclass
class Col:
    name: str
    type: str
    nullable: bool
    pk: bool = False
    comment: str | None = None
    links: list = field(default_factory=list)  # [(대상 표, 대상 열, '외래키'|'논리', 비율 문자열)]


@dataclass
class Table:
    name: str            # 스키마.표
    kind: str            # 표 / 보기
    rows: int | None
    comment: str | None
    cols: list[Col]
    reads: list[str] = field(default_factory=list)  # 보기가 읽는 표

    @property
    def schema(self) -> str:
        return self.name.split(".")[0]


# ---------------------------------------------------------------- DB 읽기

def load(url: str | None = None) -> tuple[dict[str, Table], list[dict]]:
    with db.connect(url) as conn:
        q = lambda s, p=None: conn.execute(s, p).fetchall()
        rel = q("""SELECT n.nspname || '.' || c.relname, CASE c.relkind WHEN 'v' THEN '보기' ELSE '표' END, obj_description(c.oid)
                   FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname = ANY(%s) AND c.relkind IN ('r', 'v') ORDER BY 1""", (list(SCHEMAS),))
        cols = q("""SELECT c.table_schema || '.' || c.table_name, c.column_name,
                           CASE WHEN c.data_type = 'ARRAY' THEN replace(c.udt_name, '_', '') || '[]'
                                WHEN c.data_type LIKE 'timestamp%%' THEN 'timestamptz' WHEN c.data_type = 'character varying' THEN 'varchar'
                                WHEN c.data_type = 'double precision' THEN 'double' ELSE c.data_type END,
                           c.is_nullable = 'YES',
                           col_description((c.table_schema || '.' || quote_ident(c.table_name))::regclass, c.ordinal_position)
                    FROM information_schema.columns c WHERE c.table_schema = ANY(%s) ORDER BY 1, c.ordinal_position""", (list(SCHEMAS),))
        pks = q("""SELECT tc.table_schema || '.' || tc.table_name, k.column_name FROM information_schema.table_constraints tc
                   JOIN information_schema.key_column_usage k USING (constraint_schema, constraint_name)
                   WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = ANY(%s)""", (list(SCHEMAS),))
        fks = q("""SELECT cn.nspname || '.' || cl.relname, a.attname, fn.nspname || '.' || fl.relname, fa.attname
                   FROM pg_constraint c
                   JOIN pg_class cl ON cl.oid = c.conrelid JOIN pg_namespace cn ON cn.oid = cl.relnamespace
                   JOIN pg_class fl ON fl.oid = c.confrelid JOIN pg_namespace fn ON fn.oid = fl.relnamespace
                   CROSS JOIN LATERAL unnest(c.conkey, c.confkey) AS k(child, parent)
                   JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.child
                   JOIN pg_attribute fa ON fa.attrelid = c.confrelid AND fa.attnum = k.parent
                   WHERE c.contype = 'f' AND cn.nspname = ANY(%s) ORDER BY 1, 2""", (list(SCHEMAS),))
        deps = q("""SELECT view_schema || '.' || view_name, table_schema || '.' || table_name FROM information_schema.view_table_usage
                    WHERE view_schema = ANY(%s) ORDER BY 1, 2""", (list(SCHEMAS),))
        tables = {name: Table(name, kind, None, comment, []) for name, kind, comment in rel}
        for t in tables.values():
            if t.kind == "표":
                t.rows = q(f"SELECT count(*) FROM {t.name}")[0][0]
        for t, c, typ, nullable, comment in cols:
            if t in tables:
                tables[t].cols.append(Col(c, typ, nullable, comment=comment))
        pkset = set(pks)
        for t in tables.values():
            for c in t.cols:
                c.pk = (t.name, c.name) in pkset
        for v, b in deps:
            if v in tables:
                tables[v].reads.append(b)
        links = []
        for child, col, parent, pcol in fks:
            links.append(_link(conn, child, col, [(parent, pcol)], "외래키", "선언된 외래키"))
        declared = {(l["from"], l["col"]) for l in links}
        for t in tables.values():
            if t.kind != "표" or not any(c.name == "corp_code" for c in t.cols):
                continue
            hub = HUB.get(t.schema, DEFAULT_HUB)
            if t.name == hub[0] or (t.name, "corp_code") in declared:
                continue
            links.append(_link(conn, t.name, "corp_code", [hub], "논리", "같은 회사 고유번호(DART corp_code)"))
        for child, col, targets, why in EXTRA_LINKS:
            if child in tables and all(tt in tables for tt, _ in targets):
                links.append(_link(conn, child, col, targets, "논리", why))
    for l in links:
        for c in tables[l["from"]].cols:
            if c.name == l["col"]:
                c.links.append(l)
    return tables, links


def _link(conn, child: str, col: str, targets: list[tuple[str, str]], kind: str, why: str) -> dict:
    """child.col 값 가운데 대상 표에 있는 값의 비율. 대상이 여럿이면 어느 하나에 있으면 이어진 것."""
    exists = " OR ".join(f"EXISTS (SELECT 1 FROM {t} y WHERE y.{c} = x.v)" for t, c in targets)
    sql = (f"WITH x AS (SELECT DISTINCT {col} AS v FROM {child} WHERE {col} IS NOT NULL)\n"
           f"SELECT count(*) AS 값, count(*) FILTER (WHERE {exists}) AS 이어짐 FROM x;")
    total, hit = conn.execute(sql).fetchone()
    missing = [r[0] for r in conn.execute(sql.replace("SELECT count(*) AS 값, count(*) FILTER (WHERE " + exists + ") AS 이어짐 FROM x;",
                                                      f"SELECT v FROM x WHERE NOT ({exists}) ORDER BY v LIMIT 3;")).fetchall()]
    return {"missing": missing, "from": child, "col": col, "to": [t for t, _ in targets], "to_col": targets[0][1], "kind": kind, "why": why,
            "total": total, "hit": hit, "sql": sql}


def pct(l: dict) -> str:
    return "–" if not l["total"] else f"{l['hit'] / l['total'] * 100:.1f}%"


# ---------------------------------------------------------------- 그리기

CSS = f"""
@page {{ size: A4 landscape; margin: 10mm 12mm 12mm; }}
* {{ box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
body {{ margin: 0; width: 262mm; color: {INK}; font: 500 9pt/1.5 "Gothic A1", "Apple SD Gothic Neo", sans-serif; word-break: keep-all; }}
h1, h2, h3 {{ font-family: "Do Hyeon", "Gothic A1", sans-serif; font-weight: 400; margin: 0 0 6px; }}
h1 {{ font-size: 30pt; line-height: 1.2; }} h2 {{ font-size: 18pt; }} h3 {{ font-size: 12pt; margin-top: 10px; }}
h1 em, h2 em {{ font-style: normal; color: {SEA}; }}
p {{ margin: 0 0 6px; }}
.page {{ break-before: page; page-break-before: always; }}
.tag {{ display: inline-block; font: 400 10pt "Do Hyeon"; color: #fff; background: {SEA}; border-radius: 999px; padding: 1px 12px; margin-bottom: 6px; }}
.small {{ color: {GRAY}; font-size: 8pt; line-height: 1.5; }}
.cover {{ height: 165mm; display: flex; flex-direction: column; justify-content: center; }}
.logo {{ display: flex; align-items: center; gap: 10px; font: 400 24pt "Do Hyeon"; margin-bottom: 30px; }}
.logo i {{ width: 28px; height: 28px; border-radius: 50%; background: {COIN}; box-shadow: inset 0 -4px 0 {COIN_DEEP}; display: inline-block; }}
.facts {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px; margin: 12px 0; }}
.facts div {{ background: {PAPER}; border-radius: 14px; padding: 10px 12px; }}
.facts dt {{ font-size: 8pt; color: {GRAY}; }} .facts dd {{ margin: 2px 0 0; font: 400 18pt "Do Hyeon"; color: {SEA}; }}
.cols {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; align-items: start; }}
.cols > div {{ display: flex; flex-direction: column; gap: 10px; }}
.cont {{ font: 400 11pt 'Do Hyeon'; color: {GRAY}; margin-bottom: 8px; }}
.card {{ border: 1.5px solid {LINE}; border-radius: 12px; overflow: hidden; }}
.card.view {{ border-style: dashed; }}
.card .hd {{ padding: 5px 9px; color: #fff; font-weight: 800; font-size: 8.6pt; display: flex; justify-content: space-between; gap: 6px; }}
.card .hd span {{ font-weight: 500; opacity: .9; white-space: nowrap; }}
.raw .hd {{ background: {GRAY}; }} .core .hd {{ background: {SEA}; }} .partner .hd {{ background: {COIN_DEEP}; }} .ref .hd {{ background: {INK}; }}
.view .hd {{ background: {WAVE}; color: {SEA_DEEP}; }}
.card .cm {{ padding: 4px 9px; font-size: 7.4pt; color: {GRAY}; background: {PAPER}; line-height: 1.4; }}
.card table {{ width: 100%; border-collapse: collapse; font-size: 7.4pt; }}
.card td {{ padding: 1.5px 9px; border-top: 1px solid #F0F2F5; vertical-align: top; }}
.card td.t {{ color: {GRAY}; text-align: right; white-space: nowrap; }}
.k {{ display: inline-block; font-size: 6.6pt; font-weight: 800; border-radius: 4px; padding: 0 4px; margin-right: 3px; }}
.k.pk {{ background: {COIN}; color: {INK}; }} .k.fk {{ background: {SEA}; color: #fff; }} .k.lk {{ border: 1px dashed {SEA}; color: {SEA_DEEP}; }}
.to {{ display: block; font-size: 6.8pt; color: {SEA_DEEP}; }}
.reads {{ padding: 3px 9px 5px; font-size: 7.2pt; color: {SEA_DEEP}; }}
table.list {{ width: 100%; border-collapse: collapse; font-size: 7.6pt; }}
table.list th, table.list td {{ border-bottom: 1px solid {LINE}; padding: 2px 6px; text-align: left; vertical-align: top; }}
table.list thead th {{ color: {GRAY}; border-bottom: 2px solid {INK}; }}
table.list td.n {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
tr {{ break-inside: avoid; page-break-inside: avoid; }}
pre {{ background: {INK}; color: #E5E8EE; border-radius: 10px; padding: 8px 10px; font: 7.4pt/1.45 Menlo, monospace; white-space: pre-wrap; }}
.dict h4 {{ font-size: 8.6pt; margin: 8px 0 2px; break-after: avoid; }}
svg text {{ font-family: "Gothic A1", sans-serif; }}
"""

LANES = [("raw", "원천 (raw · ref)", GRAY), ("core", "판정·분석 결과 (core 표)", SEA), ("view", "확정 값 보기 (core 보기)", SEA_DEEP), ("partner", "대조군 (partner)", COIN_DEEP)]


def lane_of(t: Table) -> str:
    if t.schema in ("raw", "ref"):
        return "raw"
    if t.schema == "partner":
        return "partner"
    return "view" if t.kind == "보기" else "core"


def overview(tables: dict[str, Table], links: list[dict]) -> str:
    """한 장 지도: 칸 4개에 표·보기 상자, 외래키·보기가 읽는 표·rcept_no 연결을 선으로. corp_code로 이어지는 표는 노란 점.

    선은 가로·세로로만 꺾이고 상자를 지나지 않는다: 상자 옆 빈 세로 통로(칸 사이)와, 상자 줄 사이 빈 가로 통로로만 다닌다.
    통로 안에서는 선마다 자리(트랙)를 따로 줘서 겹치지 않게 한다.
    """
    top, bh, gap, bw, gut = 44, 16, 14, 176, 96   # gap = 상자 줄 사이 가로 통로, gut = 칸 사이 세로 통로
    lw = bw + gut
    order = {n: i for i, (_, _, names) in enumerate(DOMAINS) for n in names}
    pos: dict[str, tuple[int, int]] = {}   # 이름 → (칸 번호, 줄 번호)
    lane_x = [8 + i * lw for i in range(len(LANES))]
    row_y = lambda j: top + j * (bh + gap)
    out = []
    rows_in = []
    for i, (key, title, color) in enumerate(LANES):
        x = lane_x[i]
        out.append(f"<text x='{x}' y='16' font-size='11' font-weight='800' fill='{color}'>{escape(title)}</text>")
        names = sorted([t for t in tables.values() if lane_of(t) == key], key=lambda t: (order.get(t.name, 99), t.name))
        rows_in.append(len(names))
        for j, t in enumerate(names):
            y = row_y(j)
            pos[t.name] = (i, j)
            fill = WAVE if t.kind == "보기" else "#fff"
            dash = " stroke-dasharray='3 2'" if t.kind == "보기" else ""
            hub = any(l["col"] == "corp_code" and l["from"] == t.name for l in links) or t.name in ("core.core_company", "partner.company")
            out.append(f"<rect x='{x}' y='{y}' width='{bw}' height='{bh}' rx='4' fill='{fill}' stroke='{color}' stroke-width='1.2'{dash}/>"
                       f"<text x='{x + 6}' y='{y + 10.5}' font-size='8.2' font-weight='{800 if t.name in ('core.core_company', 'partner.company') else 600}'>{escape(t.name.split('.', 1)[1])}</text>"
                       + (f"<text x='{x + bw - 12}' y='{y + 10.5}' font-size='7' text-anchor='end' fill='{GRAY}'>{t.rows:,}</text>" if t.rows is not None else "")
                       + (f"<circle cx='{x + bw - 5}' cy='{y + bh / 2}' r='2.6' fill='{COIN}'/>" if hub else ""))
    W = lane_x[-1] + bw + gut
    H = row_y(max(rows_in)) + 10

    edges = []  # (출발, 도착, 선 모양): 선 모양이 종류, 색은 선끼리 가려 보이게 하나씩 다르게
    for l in links:
        if l["col"] == "corp_code" and l["kind"] == "논리":
            continue
        for to in l["to"]:
            edges.append((l["from"], to, "" if l["kind"] == "외래키" else "5 3"))
    for v in tables.values():
        for b in v.reads:
            edges.append((b, v.name, "2.5 2"))
    edges = [e for e in edges if e[0] in pos and e[1] in pos]

    # 1단계: 선마다 지나갈 곳(상자 옆 구멍, 세로 통로, 가로 통로)을 정한다
    plans = []
    for a, b, dash in edges:
        (la, ra), (lb, rb) = pos[a], pos[b]
        if la == lb:
            plan = {"out": (a, "R"), "in": (b, "R"), "g": [la], "h": None}
        elif la < lb:
            plan = {"out": (a, "R"), "in": (b, "L"), "g": [la] if lb == la + 1 else [la, lb - 1], "h": None if lb == la + 1 else rb}
        else:
            plan = {"out": (a, "L"), "in": (b, "R"), "g": [la - 1] if la == lb + 1 else [la - 1, lb], "h": None if la == lb + 1 else rb}
        plans.append((a, b, dash, plan))
    # 2단계: 같은 곳을 쓰는 선끼리 자리를 고르게 나눈다 (구멍은 상자 높이 안에서, 통로는 폭 안에서)
    ports, gutters, gaps = defaultdict(list), defaultdict(list), defaultdict(list)
    for i, (a, b, _, pl) in enumerate(plans):
        ports[pl["out"]].append(i)
        ports[pl["in"]].append(i)
        for g in pl["g"]:
            gutters[g].append(i)
        if pl["h"] is not None:
            gaps[pl["h"]].append(i)
    for d in (gutters, gaps):  # 위쪽에서 시작하는 선을 바깥쪽 자리에 둬 엇갈림을 줄인다
        for k in d:
            d[k].sort(key=lambda i: (pos[plans[i][0]][1], pos[plans[i][1]][1]))

    def port_y(key, i):
        lst = ports[key]
        r = pos[key[0]][1]
        return row_y(r) + bh * (lst.index(i) + 1) / (len(lst) + 1)

    def gutter_x(g, i):
        lst = gutters[g]
        step = min(6.0, (gut - 14) / max(len(lst) - 1, 1))
        return lane_x[g] + bw + 7 + lst.index(i) * step

    def gap_y(j, i):
        lst = gaps[j]
        step = min(3.0, (gap - 5) / max(len(lst) - 1, 1))
        return row_y(j) - gap + 2.5 + lst.index(i) * step

    palette = ["#3D6BFF", "#E0A500", "#19B36B", "#F2555A", "#8B5CF6", "#0EA5E9", "#F97316", "#0F766E", "#DB2777", "#475569", "#65A30D", "#1E3A8A"]
    for i, (a, b, dash, pl) in enumerate(plans):
        color = palette[i % len(palette)]
        (la, _), (lb, _) = pos[a], pos[b]
        ya, yb = port_y(pl["out"], i), port_y(pl["in"], i)
        sx = lane_x[la] + (bw if pl["out"][1] == "R" else 0)
        tx = lane_x[lb] + (bw if pl["in"][1] == "R" else 0)
        g = [gutter_x(k, i) for k in pl["g"]]
        if pl["h"] is None:
            pts = [(sx, ya), (g[0], ya), (g[0], yb), (tx, yb)]
        else:
            hy = gap_y(pl["h"], i)
            pts = [(sx, ya), (g[0], ya), (g[0], hy), (g[1], hy), (g[1], yb), (tx, yb)]
        d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        ex, ey = pts[-1]
        arrow = -1 if pts[-2][0] > ex else 1  # 화살표는 도착 상자 쪽으로
        out.append(f"<path d='{d}' fill='none' stroke='{color}' stroke-width='1.5' stroke-dasharray='{dash}' stroke-linejoin='round'/>"
                   f"<path d='M{ex - 5 * arrow:.1f},{ey - 2.4:.1f} L{ex:.1f},{ey:.1f} L{ex - 5 * arrow:.1f},{ey + 2.4:.1f}' fill='none' stroke='{color}' stroke-width='1.3'/>"
                   f"<circle cx='{sx:.1f}' cy='{ya:.1f}' r='1.8' fill='{color}'/>")
    return f"<svg viewBox='0 0 {W} {H}' width='100%' height='148mm'>{''.join(out)}</svg>"


def card(t: Table) -> str:
    cls = f"card {t.schema}{' view' if t.kind == '보기' else ''}"
    rows = []
    for c in t.cols:
        keys = ("<span class='k pk'>PK</span>" if c.pk else "") + "".join(
            f"<span class='k {'fk' if l['kind'] == '외래키' else 'lk'}'>{'FK' if l['kind'] == '외래키' else '연결'}</span>" for l in c.links)
        to = "".join(f"<span class='to'>→ {escape(' / '.join(l['to']))}.{escape(l['to_col'])} · 이어짐 {pct(l)}</span>" for l in c.links)
        rows.append(f"<tr><td>{keys}{escape(c.name)}{'' if c.nullable or c.pk else ' *'}{to}</td><td class='t'>{escape(c.type)}</td></tr>")
    size = f"{t.rows:,}행" if t.rows is not None else "보기"
    cm = f"<div class='cm'>{escape(t.comment)}</div>" if t.comment else ""
    reads = f"<div class='reads'>읽는 표: {escape(', '.join(t.reads))}</div>" if t.reads else ""
    return f"<div class='{cls}'><div class='hd'>{escape(t.name)}<span>{size}</span></div>{cm}{reads}<table>{''.join(rows)}</table></div>"


# 인쇄 직전에 브라우저가 카드·열 사전 묶음의 실제 높이를 재서, 한 쪽(3열)에 들어가는 만큼만 담고 나머지는 다음 쪽으로 통째로 넘긴다.
# 그래서 표 하나가 쪽 끝에서 잘려 다음 쪽으로 이어지지 않는다.
PAGINATE_JS = """
// 한 쪽에 들어가는 높이: 인쇄는 화면 폭 전체(window.innerWidth)를 종이 인쇄 폭(794pt)에 맞춰 줄이므로,
// 종이 인쇄 높이(539pt)에 같은 비율을 곱한 만큼이 화면 px로 한 쪽이다 (html_to_pdf.swift: A4 가로, 여백 위아래 28pt·좌우 24pt)
function pageHeight() {
  return Math.floor(window.innerWidth * (595 - 56) / (842 - 48) * 0.93) - 16;  // 0.93: 인쇄해 보니 이 이상이면 카드 끝이 다음 쪽으로 넘침
}
// 쪽마다, 아직 안 놓은 카드를 순서대로 보며 그 쪽에서 가장 덜 찬 열 가운데 들어가는 곳에 넣는다.
// 큰 카드 하나가 안 들어간다고 바로 다음 쪽으로 넘기지 않고, 뒤의 작은 카드로 빈자리를 먼저 채운다
function pack(hs, firstCap, cap, C) {
  const left = hs.map((_, i) => i);
  const cols = [];
  let first = true;
  while (left.length) {
    const limit = first ? firstCap : cap;
    const page = Array.from({ length: C }, () => []), used = Array(C).fill(0);
    for (let k = 0; k < left.length;) {
      const i = left[k];
      let best = -1;
      used.forEach((u, c) => { if (u + hs[i] <= limit && (best < 0 || u < used[best])) best = c; });
      if (best < 0 && used.every(u => u === 0)) best = 0;  // 빈 쪽에도 안 들어가는 아주 큰 카드는 그대로 둔다
      if (best < 0) { k++; continue; }
      page[best].push(i); used[best] += hs[i]; left.splice(k, 1);
    }
    cols.push(...page);
    first = false;
  }
  return cols;
}
function paginate() {
  const PAGE = pageHeight();
  document.querySelectorAll('section.pack').forEach(sec => {
    const C = Number(sec.dataset.cols || 3), GAP = 10;
    const box = sec.querySelector('.items');
    const items = [...box.children];
    const colW = (sec.clientWidth - GAP * (C - 1)) / C;
    const meas = document.createElement('div');
    meas.style.width = colW + 'px';
    sec.appendChild(meas);
    const hs = items.map(it => { meas.appendChild(it); return it.offsetHeight + GAP; });
    meas.remove(); box.remove();
    const headH = sec.querySelector('.head').offsetHeight + 10;
    const fit = Number(sec.dataset.fit || 1);  // 긴 설명 글이 많은 열 사전은 인쇄 때 조금 더 길어져 여유를 더 둔다
    const cols = pack(hs, PAGE * fit - headH, PAGE * fit - 34, C);
    let after = sec;
    for (let k = 0; k * C < cols.length; k++) {
      const grid = document.createElement('div');
      grid.className = 'cols';
      grid.style.gridTemplateColumns = 'repeat(' + C + ', 1fr)';
      cols.slice(k * C, k * C + C).forEach(col => { const d = document.createElement('div'); col.forEach(i => d.appendChild(items[i])); grid.appendChild(d); });
      if (k === 0) { sec.appendChild(grid); continue; }
      const s = document.createElement('section');
      s.className = 'page';
      s.innerHTML = '<div class="cont">' + sec.dataset.title + ' (이어서)</div>';
      s.appendChild(grid);
      after.after(s); after = s;
    }
  });
}
// 글꼴을 다 받은 뒤에 재야 인쇄 때와 높이가 같다. 끝나면 인쇄 도구(html_to_pdf.swift)에 알린다
window.__printReady = false;
// 구글 글꼴 목록(CSS)이 늦게 오면 document.fonts.load가 바로 끝나 버린다. Gothic A1이 실제로 읽힐 때까지 기다린다(최대 8초)
const fontsLoaded = new Promise(resolve => {
  const t0 = Date.now();
  const tick = () => {
    const faces = document.fonts ? [...document.fonts] : [];
    const ready = faces.some(f => f.family.replace(/"/g, '') === 'Gothic A1');
    if (ready || Date.now() - t0 > 8000) {
      Promise.all(['500 10px "Gothic A1"', '700 10px "Gothic A1"', '800 10px "Gothic A1"', '10px "Do Hyeon"']
        .map(f => document.fonts.load(f).catch(() => null))).then(() => document.fonts.ready).then(resolve);
    } else setTimeout(tick, 100);
  };
  tick();
});
fontsLoaded.then(() => new Promise(r => setTimeout(r, 100))).then(() => { paginate(); window.__printReady = true; });
"""


def build(tables: dict[str, Table], links: list[dict]) -> str:
    base = [t for t in tables.values() if t.kind == "표"]
    views = [t for t in tables.values() if t.kind == "보기"]
    fk = [l for l in links if l["kind"] == "외래키"]
    lk = [l for l in links if l["kind"] == "논리"]
    by_schema = defaultdict(int)
    for t in base:
        by_schema[t.schema] += 1
    cover = f"""<section class='cover'><div class='logo'><i></i>원픽</div>
<h1>onepick DB<br><em>전체 ERD</em></h1>
<p>PostgreSQL <b>onepick</b> 데이터베이스의 스키마 {len(SCHEMAS)}개(raw · ref · core · partner), 표 {len(base)}개, 보기 {len(views)}개, 열 {sum(len(t.cols) for t in tables.values()):,}개를 지금 DB에서 바로 읽어 그렸어요.
선언된 외래키 {len(fk)}개는 실선, 같은 키로 잇는 논리 연결 {len(lk)}개는 점선이고, 연결마다 실제로 이어지는 값의 비율을 세어 적었어요.</p>
<div class='facts'>{''.join(f"<div><dt>{s} 표</dt><dd>{by_schema.get(s, 0)}</dd></div>" for s in SCHEMAS)}<div><dt>보기</dt><dd>{len(views)}</dd></div><div><dt>전체 행</dt><dd>{sum(t.rows for t in base) / 1e6:.1f}M</dd></div></div>
<p class='small'>만든 날 {date.today().isoformat()} · 코드 source/scripts/report_erd_pdf.py · 표 정의 source/db/schema.sql, source/db/schema_capital.sql · 스키마 뜻: raw = 공시·KRX·한국은행 원천 그대로, ref = 세율표, core = 검증·판정·분석 결과와 확정 값 보기, partner = 대조군 데이터</p></section>"""

    legend = (f"<p class='small'>상자 = 표(실선) · 보기(점선, 연한 파랑) · 오른쪽 숫자 = 행 수 · <b style='color:{COIN_DEEP}'>노란 점</b> = corp_code로 회사 표(core.core_company / partner.company)에 이어짐 · "
              "선 모양: <b>실선</b> = 선언된 외래키 · <b>긴 점선</b> = rcept_no 논리 연결 · <b>짧은 점선</b> = 보기가 읽는 표 · "
              "선 색은 종류가 아니라 선끼리 가려 보이게 하나씩 다르게 했어요 · 작은 점 = 출발, 화살표 = 도착(읽히는 표·참조되는 표)</p>")
    over = f"<section class='page'><span class='tag'>전체 지도</span><h2>자료가 흐르는 길: <em>원천 → 결과 → 확정 값 보기</em></h2>{legend}{overview(tables, links)}</section>"

    placed = {n for _, _, names in DOMAINS for n in names}
    rest = [n for n in sorted(tables) if n not in placed]
    domains = DOMAINS + ([("그 밖", "위 영역에 넣지 않은 표", rest)] if rest else [])
    pages = []
    for i, (title, desc, names) in enumerate(domains, 1):
        ts = [tables[n] for n in names if n in tables]
        pages.append(f"<section class='page pack' data-cols='4' data-title='영역 {i} · {escape(title)}'><div class='head'><span class='tag'>영역 {i}</span><h2>{escape(title)}</h2><p class='small'>{escape(desc)} · 표 {sum(t.kind == '표' for t in ts)}개 · 보기 {sum(t.kind == '보기' for t in ts)}개 · "
                     "<span class='k pk'>PK</span> 기본키 <span class='k fk'>FK</span> 선언된 외래키 <span class='k lk'>연결</span> 같은 키로 잇는 논리 연결 · * = 빈칸 안 됨</p></div>"
                     f"<div class='items'>{''.join(card(t) for t in ts)}</div></section>")

    link_rows = "".join(
        f"<tr><td>{'외래키' if l['kind'] == '외래키' else '논리'}</td><td>{escape(l['from'])}.{escape(l['col'])}</td><td>{escape(' / '.join(l['to']))}.{escape(l['to_col'])}</td>"
        f"<td class='n'>{l['total']:,}</td><td class='n'>{l['hit']:,}</td><td class='n'><b>{pct(l)}</b></td><td>{escape(l['why'])}</td><td>{escape(', '.join(l['missing']))}</td></tr>"
        for l in sorted(links, key=lambda l: (l["kind"] != "외래키", l["from"])))
    sample = next(l for l in links if l["from"] == "core.core_event_car" and l["col"] == "rcept_no")
    linkpage = (f"<section class='page'><span class='tag'>연결 확인</span><h2>표끼리 <em>정말 이어지나</em></h2>"
                "<p>연결마다 왼쪽 표의 키 값(중복 없이) 가운데 오른쪽 표에 있는 값의 수를 셌어요. 100%가 아니면 왼쪽에 회사 목록 밖의 회사(예: 공시 목록 전체)나 오른쪽에 아직 안 모은 공시가 있다는 뜻이에요.</p>"
                "<table class='list'><thead><tr><th>종류</th><th>표.열</th><th>잇는 곳</th><th>값</th><th>이어짐</th><th>비율</th><th>뜻</th><th>안 이어진 값(최대 3)</th></tr></thead>"
                f"<tbody>{link_rows}</tbody></table>"
                f"<h3>직접 세어 보는 법 (예: {escape(sample['from'])}.{escape(sample['col'])})</h3><pre>{escape(sample['sql'])}</pre></section>")

    view_rows = "".join(f"<tr><td>{escape(v.name)}</td><td>{escape(', '.join(v.reads))}</td><td>{escape(v.comment or '')}</td></tr>" for v in views)
    viewpage = (f"<section class='page'><span class='tag'>보기</span><h2>확정 값 <em>보기 {len(views)}개</em></h2>"
                "<p class='small'>보기는 저장된 표가 아니라, 부를 때마다 아래 표를 읽어 계산해요. 화면과 분석은 대부분 *_verified 보기(팀 검토 확정 값 우선)를 읽어요. 출처 information_schema.view_table_usage.</p>"
                f"<table class='list'><thead><tr><th>보기</th><th>읽는 표</th><th>설명</th></tr></thead><tbody>{view_rows}</tbody></table></section>")

    dict_parts = []
    for t in sorted(tables.values(), key=lambda t: (SCHEMAS.index(t.schema), t.name)):
        rows = "".join(f"<tr><td>{'🔑 ' if c.pk else ''}{escape(c.name)}</td><td>{escape(c.type)}</td><td>{'' if c.nullable else '필수'}</td><td>{escape(c.comment or '')}</td></tr>" for c in t.cols)
        dict_parts.append(f"<div><h4>{escape(t.name)} <span class='small'>{t.kind}{f' · {t.rows:,}행' if t.rows is not None else ''}</span></h4>"
                          f"<table class='list'><tbody>{rows}</tbody></table></div>")
    dictpage = f"<section class='page pack' data-cols='3' data-fit='0.86' data-title='열 사전'><div class='head'><span class='tag'>열 사전</span><h2>모든 표의 <em>열</em></h2><p class='small'>열 설명은 DB에 적어 둔 COMMENT예요(없으면 빈칸). 🔑 = 기본키.</p></div><div class='items'>{''.join(dict_parts)}</div></section>"

    return (f"<html><head><meta charset='utf-8'><link href='https://fonts.googleapis.com/css2?family=Do+Hyeon&family=Gothic+A1:wght@400;500;700;800&display=swap' rel='stylesheet'>"
            f"<style>{CSS}</style></head><body>{cover}{over}{''.join(pages)}{linkpage}{viewpage}{dictpage}<script>{PAGINATE_JS}</script></body></html>")


def main(url: str, out: Path, html_only: bool) -> None:
    tables, links = load(url)
    html = build(tables, links)
    if html_only:
        out.with_suffix(".html").write_text(html, encoding="utf-8")
        print(out.with_suffix(".html"))
        return
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "erd.html"
        page.write_text(html, encoding="utf-8")
        r = subprocess.run(["swift", str(ROOT / "source" / "scripts" / "html_to_pdf.swift"), str(page), str(out), "landscape"], capture_output=True, text=True)
        if r.returncode != 0 or not out.exists():
            raise SystemExit(f"PDF 만들기 실패: {r.stderr[-500:]}")
    print(out, f"표 {sum(t.kind == '표' for t in tables.values())}개 · 보기 {sum(t.kind == '보기' for t in tables.values())}개 · 연결 {len(links)}개")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="onepick DB 전체 ERD PDF")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--url", default=db.database_url())
    ap.add_argument("--html-only", action="store_true")
    a = ap.parse_args()
    main(a.url, a.out, a.html_only)
