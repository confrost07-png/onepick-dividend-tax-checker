"""F-06 재무 여력 표 core.core_capacity_2025를 만든다 (source/scripts/build_judgement.py 다음에 실행).

실행: .venv/bin/python -m scripts.build_capacity [--url ...]
업종명은 DART 기업개황(source/scripts/verify_sources.py가 받아 둔 캐시)에서 읽는다. 지표 규칙은 source/core/capacity.py.
"""
import argparse
from collections import Counter, defaultdict

from core import capacity as cp
from core import db
from core import source_verify as sv

OCF = "ifrs-full_CashFlowsFromUsedInOperatingActivities"
CAPEX = ("ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities", "ifrs-full_PurchaseOfPropertyPlantAndEquipment")


def main(url: str):
    with db.connect(url) as conn:
        db.apply_schema(conn)
        companies = db.fetch_dicts(conn, "SELECT corp_code, corp_name FROM core.core_company ORDER BY corp_code")
        cf = defaultdict(dict)
        for r in db.fetch_dicts(conn, f"""SELECT corp_code, fs_div, account_id, thstrm_amount, rcept_no FROM raw.dart_financial
                                         WHERE bsns_year = 2025 AND sj_div = 'CF' AND account_id IN ('{OCF}', '{CAPEX[0]}', '{CAPEX[1]}')
                                         ORDER BY ord"""):
            d = cf[r["corp_code"]]
            d.setdefault("fs_div", r["fs_div"])
            d.setdefault("rcept_no", r["rcept_no"])
            key = "ocf" if r["account_id"] == OCF else "capex"
            if r["fs_div"] == d["fs_div"] and key not in d and r["thstrm_amount"] is not None:
                d[key] = float(r["thstrm_amount"])
        fin = {r["corp_code"]: r for r in db.fetch_dicts(
            conn, "SELECT * FROM core.v_financial_year_verified WHERE bsns_year = 2025")}
        # 2025년(기본) 시나리오: 2025 순이익이 최저·최고와 같으면 그 이름으로 합쳐져 있어 순이익으로 찾는다.
        # 최소액 계산(build_judgement)과 같은 확정 값(verified 뷰)으로 찾아야 원문 대조로 고친 회사도 맞게 찾는다
        ni25 = {code: r["ni_owner_won"] for code, r in fin.items()}
        mins = {r["corp_code"]: r for r in db.fetch_dicts(conn, "SELECT * FROM core.core_min_dividend_2027 WHERE status = '산출'")
                if r["scenario"] == "2025년 (기본)" or r["ni2026_won"] == ni25.get(r["corp_code"])}
        rows = []
        for c in companies:
            code = c["corp_code"]
            industry = sv.company_info(code).get("industry")
            d, f, m = cf.get(code, {}), fin.get(code, {}), mins.get(code)
            x = cp.capacity(industry, d.get("ocf"), d.get("capex"), float(m["min_won"]) if m else None,
                            f.get("ni_owner_won") and float(f["ni_owner_won"]), f.get("liabilities_won") and float(f["liabilities_won"]),
                            f.get("equity_won") and float(f["equity_won"]), name=c["corp_name"])
            rows.append({"corp_code": code, "industry": industry, "status": x.status, "fs_div": d.get("fs_div"),
                         "ocf_won": d.get("ocf"), "capex_won": abs(d["capex"]) if d.get("capex") is not None else None,
                         "fcf_won": x.fcf, "min_won": float(m["min_won"]) if m else None, "cover_x": x.cover,
                         "roe_pct": x.roe_pct, "debt_pct": x.debt_pct, "industry_median_cover": None, "median_basis": None,
                         "rcept_no": d.get("rcept_no"), "note": x.note})
        by_ind = defaultdict(list)
        for r in rows:
            if r["cover_x"] is not None:
                by_ind[r["industry"]].append(r["cover_x"])
        overall = [v for vs in by_ind.values() for v in vs]
        for r in rows:
            if r["status"] == cp.SHOWN:
                r["industry_median_cover"], r["median_basis"] = cp.industry_median(by_ind, r["industry"], overall)
        n = db.replace_rows(conn, "core.core_capacity_2025", rows)
        conn.commit()
    print(f"  core.core_capacity_2025: {n}행 · " + " · ".join(f"{k} {v}" for k, v in Counter(r["status"] for r in rows).items()))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="F-06 재무 여력 표 만들기")
    ap.add_argument("--url", default=db.database_url(), help="PostgreSQL 주소")
    main(ap.parse_args().url)
