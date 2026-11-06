"""이벤트 스터디 유의성 보고서 PDF (색 구분) → report/분석/이벤트스터디_유의성_보고서.pdf.

실행: .venv/bin/python -m scripts.report_event_pdf   (scripts.build_events 다음에, 숫자는 scripts.event_methods와 같은 계산)
색 규칙
- p값 칸: 붉은색 p < 0.05 · 푸른색 p ≥ 0.10 · 검은색 그 사이
- 결론 칸(묶음 전체): 붉은색 = 날짜 몰림을 보정한 네 검정(공시일 군집 t·KP 보정 BMP·일반화 부호·윌콕슨)이 모두 p < 0.05이고
  다중비교 보정 q < 0.05 / 푸른색 = 네 검정이 모두 p ≥ 0.10 / 검은색 = 방법에 따라 갈림
PDF는 macOS WebKit으로 인쇄한다 (source/scripts/html_to_pdf.swift).
"""
import argparse
import subprocess
import tempfile
from datetime import date
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd

from core import db
from core import event_study as es
from scripts import event_methods as em
from scripts.event_significance import mann_whitney

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "report" / "분석" / "이벤트스터디_유의성_보고서.pdf"
RED, BLUE, BLACK = "sig", "nul", "mid"
ROBUST = ["공시일 군집 t p", "KP 보정 BMP p", "일반화 부호 p", "윌콕슨 p"]


def p_class(p) -> str:
    if p is None or pd.isna(p):
        return ""
    return RED if p < 0.05 else BLUE if p >= 0.10 else BLACK


def verdict(row) -> tuple[str, str]:
    ps = [row.get(c) for c in ROBUST]
    if any(p is None or pd.isna(p) for p in ps):
        return BLACK, "판단 보류(검정 일부 없음)"
    if all(p < 0.05 for p in ps) and row.get("KP p BH 보정 q", 1) < 0.05:
        return RED, "유의 (모든 방법 일치)"
    if all(p >= 0.10 for p in ps):
        return BLUE, "무의미"
    return BLACK, "방법에 따라 갈림"


def fmt_p(p) -> str:
    return "" if p is None or pd.isna(p) else ("< 0.0001" if p < 0.0001 else f"{p:.4f}")


def table(df: pd.DataFrame, p_cols: list[str], verdict_col: str | None = None) -> str:
    head = "".join(f"<th>{escape(c)}</th>" for c in df.columns)
    body = []
    for r in df.to_dict("records"):
        cells = []
        for c in df.columns:
            v = r[c]
            if c in p_cols:
                cells.append(f'<td class="num {p_class(v)}">{fmt_p(v)}</td>')
            elif c == verdict_col:
                cls, text = v
                cells.append(f'<td class="{cls} b">{escape(text)}</td>')
            elif isinstance(v, float):
                cells.append(f'<td class="num">{"" if pd.isna(v) else f"{v:,.2f}"}</td>')
            else:
                cells.append(f'<td>{escape(str(v))}</td>')
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def group_compare(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (basis, w, model, ret), g in df[df["kind"].str.startswith("주당배당금") & ~df["overlap"]].groupby(
            ["basis", "window", "model", "ret"]):
        a = g[g["kind"] == es.DPS_UP]["car"].to_numpy()
        b = g[g["kind"] == es.DPS_FLAT_DOWN]["car"].to_numpy()
        if len(a) < 10 or len(b) < 10:
            continue
        rows.append({"기준일": basis, "창": w, "모형": model, "수익률": ret, "증가 중앙값(%p)": float(np.median(a) * 100),
                     "유지·감소 중앙값(%p)": float(np.median(b) * 100), "차이(%p)": float((np.median(a) - np.median(b)) * 100),
                     "만-위트니 p": mann_whitney(a, b)})
    return pd.DataFrame(rows)


CSS = """
body { font-family: -apple-system, 'Apple SD Gothic Neo', sans-serif; font-size: 9.5px; color: #111; }
h1 { font-size: 20px; margin: 0 0 4px; } h2 { font-size: 14px; margin: 18px 0 6px; border-bottom: 1px solid #ccc; }
p, li { line-height: 1.5; } .muted { color: #555; }
table { border-collapse: collapse; width: 100%; margin: 4px 0 10px; page-break-inside: auto; }
tr { page-break-inside: avoid; } thead { display: table-header-group; }
th { background: #1F3864; color: #fff; font-weight: 600; padding: 3px 4px; font-size: 8.5px; }
td { border-bottom: 1px solid #ddd; padding: 2px 4px; font-size: 8.5px; } td.num { text-align: right; }
.sig { color: #C00000; } .nul { color: #1F4EA8; } .mid { color: #111; } .b { font-weight: 700; }
.legend span { display: inline-block; margin-right: 14px; font-weight: 700; }
.box { border: 1px solid #ccc; padding: 8px 10px; margin: 6px 0; }
.pb { page-break-before: always; }
"""


def build_html(t, comp, reg60, n60, reg20, n20, rega, na, cal) -> str:
    t = t.copy()
    t["결론"] = [verdict(r) for r in t.to_dict("records")]
    p_t = [c for c in t.columns if c.endswith(" p") or c.endswith(" q")]
    cols = ["공시 종류", "기준일", "창", "모형", "수익률", "사례", "평균(%p)", "중앙값(%p)"] + p_t + ["결론"]
    counts = pd.Series([v[1] for v in t["결론"]]).value_counts()
    key = [
        (RED, "배당을 늘린 공시 뒤 60거래일 초과수익은 0보다 크다 (공시일·주총일, 두 모형, 배당 포함·주가만 모두)"),
        (RED, "배당수익률이 높을수록 공시 뒤 수익이 크다 (회귀 세 사양 모두, 공시일 군집 표준오차)"),
        (BLACK, "배당을 늘린 회사가 유지·감소한 회사보다 더 올랐다: 시장조정 모형에선 유의, 시장모형에선 아님"),
        (BLACK, "무상증자 공시 뒤 20일 상승: 다중비교 보정 후 경계(q ≈ 0.045), 60일엔 사라짐"),
        (BLUE, "주당배당금 증가 폭(%)이 클수록 더 오른다: 통제 변수를 넣은 회귀에서 무의미"),
        (BLUE, "감자·유상증자·주식분할 공시 뒤 주가 반응: 어떤 방법으로도 무의미"),
        (BLUE, "실적 공시가 같은 날 겹친 것은 결과를 바꾸지 않았다 (계수 무의미)"),
    ]
    reg_html = "".join(f"<h3>{escape(name)}</h3>" + table(df, ["p"]) for name, df in (
        (f"시장모형 · 배당 포함 · 60거래일 ({n60}건)", reg60), (f"시장모형 · 배당 포함 · 20거래일 ({n20}건)", reg20),
        (f"시장조정 · 배당 포함 · 60거래일 ({na}건)", rega)))
    return f"""<html><head><meta charset="utf-8"><style>{CSS}</style></head><body>
<h1>배당·자본 변동 공시 뒤 주가 반응 — 유의성 보고서</h1>
<p class="muted">만든 날 {date.today().isoformat()} · onepick DB core.core_event_car (2025년까지 공시, 자본 변동 겹침 제외) ·
코드 source/scripts/report_event_pdf.py, source/core/event_stats.py · 대상 2026 고배당기업 638곳</p>
<div class="box legend"><span class="sig">붉은색: 유의 (p &lt; 0.05 / 모든 방법 일치)</span>
<span class="mid">검은색: 경계·방법에 따라 갈림 (0.05 ≤ p &lt; 0.10)</span>
<span class="nul">푸른색: 무의미 (p ≥ 0.10)</span></div>
<p>결론 칸 규칙: 날짜 몰림을 보정한 네 검정(공시일 군집 t · Kolari–Pynnönen 보정 BMP · 일반화 부호 · 윌콕슨)이 모두 p &lt; 0.05이고
다중비교(Benjamini–Hochberg) 보정 q &lt; 0.05면 붉은색, 넷 모두 p ≥ 0.10이면 푸른색, 그 밖은 검은색.</p>
<h2>핵심 결론</h2><ul>{''.join(f'<li class="{c}">{escape(s)}</li>' for c, s in key)}</ul>
<p>묶음 {len(t)}개 중 결론: {' · '.join(f'{k} {v}' for k, v in counts.items())}</p>
<h2>방법</h2><ul>
<li>초과수익: 시장조정(종목 − 지수) / 시장모형(이벤트 전 250~30거래일로 α·β 추정)</li>
<li>수익률: 주가만 / 배당 포함(창 안 배당락일에 주당배당금 ÷ 전일 종가를 더함, 수정주가는 현금배당락을 보정하지 않음)</li>
<li>기준일: 공시일 / 주주총회 결의일(주총 예정일) / 배당락일(기준일 직전 거래일)</li>
<li>한계: 실적 서프라이즈 크기 미통제(겹침 여부만), 시가총액 추정치, 생존 편향(2026 고배당기업만), 주총일은 예정일</li></ul>
<h2 class="pb">1. CAR이 0과 다른가 — 묶음 × 방법별 p값</h2>
{table(t[cols], p_t, "결론")}
<h2 class="pb">2. 배당을 늘린 회사 vs 유지·감소한 회사 (만-위트니)</h2>
{table(comp, ["만-위트니 p"])}
<h2>3. 무엇이 CAR을 설명하나 — 횡단면 회귀 (공시일 군집 표준오차, 계수 단위 %p)</h2>
{reg_html}
<h2>4. 달력시간 포트폴리오 (공시일, 시장조정, 배당 포함, 뉴이-웨스트)</h2>
{table(cal, ["p (뉴이-웨스트)"])}
</body></html>"""


def main(url: str, out: Path):
    prices, markets, ev, dec, earn, size = em.load(url)
    df = em.compute(prices, markets, ev)
    t = em.tests(df)
    change = em.dps_change(dec)
    reg60, n60 = em.regression(df, change, earn, size, es.BASIS_DISCLOSED, 60, "시장모형", "배당 포함")
    reg20, n20 = em.regression(df, change, earn, size, es.BASIS_DISCLOSED, 20, "시장모형", "배당 포함")
    rega, na = em.regression(df, change, earn, size, es.BASIS_DISCLOSED, 60, "시장조정", "배당 포함")
    cal = pd.concat([em.calendar_time(df, prices, markets, ev, w, "배당 포함") for w in (20, 60)], ignore_index=True)
    html = build_html(t, group_compare(df), reg60, n60, reg20, n20, rega, na, cal)
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "report.html"
        page.write_text(html, encoding="utf-8")
        r = subprocess.run(["swift", str(ROOT / "source" / "scripts" / "html_to_pdf.swift"), str(page), str(out), "landscape"],
                           capture_output=True, text=True)
        if r.returncode != 0 or not out.exists():
            raise SystemExit(f"PDF 만들기 실패: {r.stderr[-500:]}")
    print(out, f"묶음 {len(t)}개")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="이벤트 스터디 유의성 보고서 PDF")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--url", default=db.database_url(), help="PostgreSQL 주소")
    a = ap.parse_args()
    main(a.url, a.out)
