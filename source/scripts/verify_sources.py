"""원천 표를 DART 원문에서 다시 읽어 칸마다 대조 → core.core_source_verify. 원본 표는 고치지 않는다.

실행: .venv/bin/python -m scripts.verify_sources [--only company,item,decision,kind] [--limit N] [--url ...]
- company : core.core_company ↔ DART 기업개황 (공시회사명·종목코드·시장·결산월)
- item    : raw.dart_dividend_item 모든 칸 ↔ 그 사업보고서 '배당에 관한 사항' 표
- decision: raw.dividend_decision 모든 칸 ↔ 그 배당 결정 공시 본문
- kind    : raw.kind_list ↔ 그 고배당기업 공시 본문
원문은 data/raw/dart_cache/에 저장되어 다시 돌리면 받지 않는다. 묶음마다 그 묶음의 행만 지우고 다시 넣는다.
DART가 막혔을 때는 DART_OFFLINE=1 로 받아 둔 원문만 대조한다 (캐시에 없는 칸은 원문에서 못 찾음).
"""
import argparse
import re
from collections import Counter, defaultdict

from psycopg import sql

from core import dart_doc as dd
from core import db
from core import source_verify as sv


def log(rows, label):
    n = Counter(r["result"] for r in rows)
    print(f"  {label}: {len(rows):,}칸 · " + " · ".join(f"{k} {v:,}" for k, v in n.most_common()), flush=True)
    return rows


def norm_name(s):
    return re.sub(r"\s|주식회사|\(주\)|㈜", "", s or "").upper()


def company(conn, limit=None):
    rows = []
    for c in db.fetch_dicts(conn, "SELECT * FROM core.core_company ORDER BY corp_code")[:limit]:
        try:
            info = sv.company_info(c["corp_code"])
        except Exception as e:  # noqa: BLE001 네트워크 오류는 칸에 적고 다음 회사로
            info = {}
            print(f"    {c['corp_name']}: {e}", flush=True)
        key, corp = c["corp_code"], c["corp_code"]
        rows += [sv.result("core_company", corp, None, key, "corp_name", norm_name(c["corp_name"]),
                           norm_name(info["name"]) if "name" in info else None, "", note=info.get("name", "")),
                 sv.result("core_company", corp, None, key, "stock_code", c["stock_code"], info.get("stock_code"), ""),
                 sv.result("core_company", corp, None, key, "market", c["market"],
                           sv.MARKET.get(info.get("market"), info.get("market")), "", note=info.get("market", "")),
                 sv.result("core_company", corp, None, key, "fiscal_month", c["fiscal_month"], info.get("fiscal_month"), "")]
    return log(rows, "회사 목록")


def items(conn, limit=None):
    raw = defaultdict(list)
    for r in db.fetch_dicts(conn, "SELECT * FROM raw.dart_dividend_item ORDER BY rcept_no, bsns_year, ctid"):
        raw[r["rcept_no"]].append(r)
    rows = []
    for n, (rcp, rs) in enumerate(list(raw.items())[:limit]):
        corp = rs[0]["corp_code"]
        top = max(r["bsns_year"] for r in rs)  # 보고서 당기 = 이 보고서가 준 가장 늦은 사업연도
        try:
            _, lines = sv.dividend_section(rcp)
            table = sv.dividend_table(lines)
        except Exception as e:  # noqa: BLE001
            table = []
            print(f"    {rcp}: {e}", flush=True)
        parsed = defaultdict(list)
        for item, kind, vals in table:
            parsed[(item, re.sub(r"\s", "", kind))].append(vals)
        seen = Counter()
        for r in rs:
            key = (sv.item_key(r["item"]), re.sub(r"\s", "", r["stock_kind"] or "-"))
            seen[(key, r["bsns_year"])] += 1
            nth = seen[(key, r["bsns_year"])]
            got = parsed.get(key, [])
            col = top - r["bsns_year"]
            src = got[nth - 1][col] if len(got) >= nth and len(got[nth - 1]) > col else None
            dbv = "-" if r["is_dash"] == "예" else r["value"]
            ref = f"{rcp}|{r['bsns_year']}|{r['item']}|{r['stock_kind']}|{nth}"
            note = "" if table else "배당 표를 못 읽음"
            rows.append(sv.result("dart_dividend_item", corp, r["bsns_year"], ref, r["item"], dbv, src, rcp, note=note))
        if n % 200 == 0:
            print(f"    배당 표 {n:,}/{len(raw):,}", flush=True)
    return log(rows, "배당 표 전체 항목")


def decisions(conn, limit=None):
    rows = []
    rs = db.fetch_dicts(conn, "SELECT * FROM raw.dividend_decision ORDER BY rcept_no")[:limit]
    for n, r in enumerate(rs):
        try:
            got = sv.decision_all(dd.body_lines(r["rcept_no"]))
        except Exception as e:  # noqa: BLE001
            got = {}
            print(f"    {r['rcept_no']}: {e}", flush=True)
        note = "" if got else "본문을 못 읽음"
        for f in sv.DECISION_FIELDS:
            dbv = r[f]
            if f == "total_won" and dbv is not None:
                dbv = f"{dbv:.0f}"
            rows.append(sv.result("dividend_decision", r["corp_code"], r["attributed_year"], r["rcept_no"], f, dbv, got.get(f),
                                  r["rcept_no"], note=note))
        if n % 300 == 0:
            print(f"    결정 공시 {n:,}/{len(rs):,}", flush=True)
    return log(rows, "배당 결정 공시")


def kind(conn, limit=None):
    rows = []
    for r in db.fetch_dicts(conn, "SELECT * FROM raw.kind_list ORDER BY corp_code")[:limit]:
        rcp = r["final_rcept_no"]
        try:
            got = sv.kind_fields(dd.body_lines(rcp)) if rcp else {}
        except Exception as e:  # noqa: BLE001
            got = {}
            print(f"    {rcp}: {e}", flush=True)
        for f in sv.KIND_FIELDS:
            dbv = r[f]
            if isinstance(dbv, (int, float)) or dbv.__class__.__name__ == "Decimal":
                dbv = f"{dbv:f}".rstrip("0").rstrip(".") if "." in f"{dbv:f}" else f"{dbv:f}"
            rows.append(sv.result("kind_list", r["corp_code"], None, rcp or r["corp_code"], f,
                                  None if dbv is None else str(dbv), got.get(f), rcp or "", note="" if got else "본문을 못 읽음"))
    return log(rows, "KIND 고배당 공시")


PARTS = {"company": ("core_company", company), "item": ("dart_dividend_item", items),
         "decision": ("dividend_decision", decisions), "kind": ("kind_list", kind)}


def save(conn, target: str, rows: list[dict]):
    conn.execute("DELETE FROM core.core_source_verify WHERE target = %s", (target,))
    if rows:
        cols = list(rows[0])
        copy = sql.SQL("COPY core.core_source_verify ({}) FROM STDIN").format(sql.SQL(", ").join(map(sql.Identifier, cols)))
        with conn.cursor().copy(copy) as cp:
            for r in rows:
                cp.write_row([r[c] for c in cols])
    conn.commit()


def main(url: str, only: list[str], limit=None):
    with db.connect(url) as conn:
        db.apply_schema(conn)
        conn.commit()
        for name in only:
            target, fn = PARTS[name]
            rows = fn(conn, limit)
            if limit is None:
                save(conn, target, rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="원천 표를 DART 원문과 칸마다 대조")
    ap.add_argument("--only", default="company,kind,item,decision", help="할 묶음 (쉼표)")
    ap.add_argument("--limit", type=int, default=None, help="시험용: 앞에서 N건만 보고 저장하지 않음")
    ap.add_argument("--url", default=db.database_url(), help="PostgreSQL 주소")
    a = ap.parse_args()
    main(a.url, a.only.split(","), a.limit)
