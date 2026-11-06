"""데이터셋 기간(배당 2017~·주가 2018~)에 맞춰 2016~2026 거시지표를 한국은행 ECOS에서 받아 CSV로 저장한다.

실행: .venv/bin/python -m scripts.collect_macro [--only 이름,...] [--out 폴더]
키: 환경변수 ECOS_API_KEY, 없으면 .env(워크트리면 메인 폴더 .env)에서 읽는다. 키는 출력·파일에 남기지 않는다.
저장: data/raw/macro/<지표>.csv (원문 값 그대로, git 제외)와 출처표 _sources.csv. 다시 돌리면 덮어쓴다.
"""
import argparse
import csv
from datetime import date
from pathlib import Path

from core import macro as m


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)


def collect(out: Path, only: set[str] | None = None) -> list[dict]:
    key = m.api_key()
    if not key:
        raise SystemExit("ECOS_API_KEY를 찾지 못함 (환경변수 또는 .env)")
    out.mkdir(parents=True, exist_ok=True)
    sources = []
    for s in m.SERIES:
        if only and s.name not in only:
            continue
        rows = m.fetch(key, s)
        write_csv(out / f"{s.name}.csv", rows, m.COLUMNS)
        first = rows[0] if rows else {}
        sources.append({
            "series": s.name, "label": s.label, "rows": len(rows),
            "first": first.get("time"), "last": rows[-1]["time"] if rows else None,
            "unit": first.get("unit"), "stat_code": s.stat_code, "stat_name": first.get("stat_name"),
            "item_code1": s.item_code, "item_code2": "" if s.item_code2 == "?" else s.item_code2, "cycle": s.cycle,
            "source": "한국은행 ECOS Open API StatisticSearch", "fetched": date.today().isoformat(),
        })
        print(f"  {s.name}: {len(rows):,}행 {sources[-1]['first']}~{sources[-1]['last']} ({sources[-1]['unit']})")
    if not only:
        write_csv(out / "_sources.csv", sources, list(sources[0]))
    return sources


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="ECOS 거시지표(경상수지·금리·환율·GDP·CPI·고용)를 CSV로 저장")
    ap.add_argument("--only", help="받을 지표 이름(쉼표로 구분). 주면 _sources.csv는 건드리지 않는다")
    ap.add_argument("--out", type=Path, default=m.OUT_DIR, help="저장 폴더")
    args = ap.parse_args()
    collect(args.out, set(args.only.split(",")) if args.only else None)
