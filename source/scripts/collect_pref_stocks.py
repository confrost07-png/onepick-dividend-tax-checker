"""고배당기업 638곳의 상장 우선주 종목 → raw.krx_pref_stock, 그리고 core.core_company의 우선주 칸을 고친다.

실행: .venv/bin/python -m scripts.collect_pref_stocks [--url ...]
- 원천 엑셀 07의 '상장우선주_코드' 칸이 638곳 모두 비어 있어, 삼성전자우처럼 상장된 우선주도 '상장 우선주 없음'으로 적혀 있었다.
- KRX 정보데이터시스템은 로그인이 필요해져서, 대조군 주가와 같은 네이버 금융 차트(공개 자료)로 종목코드를 하나씩 조회한다.
  우선주 코드는 보통주 코드 앞 5자리가 같고 끝 한 글자만 다르다(예: 005930 → 005935, 000880 → 00088K).
  후보 끝 글자 CANDIDATE_TAILS를 모두 물어보고, 종목명이 우선주 모양(…우, …2우B, …우(전환))인 것만 남긴다.
- 마지막 거래일이 전체 최신 거래일에서 LISTED_DAYS일 안이면 '상장 중', 아니면 '거래 없음(상장폐지 추정)'.
- 받은 응답은 data/raw/naver_fchart_pref/{코드}.txt에 둔다(git 제외). 없는 코드도 빈 파일로 남겨 다시 묻지 않는다.
- 인터넷 조회는 DB 연결을 닫은 채로 한다(조회 중 표를 잠그지 않게). 조회는 WORKERS개씩 함께 보낸다.
"""
import argparse
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path

from core import db
from core.chat_parse import _PREFERRED

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "raw" / "naver_fchart_pref"
URL = "https://fchart.stock.naver.com/sise.nhn?symbol={}&timeframe=day&count=1&requestType=0"
SOURCE = "네이버 금융 차트(fchart) 종목명·마지막 거래일"
CANDIDATE_TAILS = "579KLMN"  # 우(5)·2우B(7)·3우B(9), 2019년 뒤 새 형식(K·L·M·N)
LISTED_DAYS = 14
WORKERS = 6
LISTED, GONE = "상장 중", "거래 없음(상장폐지 추정)"
_NAME = re.compile(r'<chartdata[^>]*name="([^"]*)"')
_LAST = re.compile(r'data="(\d{8})\|')


def fetch(code: str, pause: float = 0.12) -> str:
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"{code}.txt"
    if p.exists():
        return p.read_text(encoding="utf-8")
    for wait in (0, 2, 10):
        time.sleep(wait or pause)
        try:
            text = urllib.request.urlopen(URL.format(code), timeout=30).read().decode("euc-kr", "replace")
        except OSError:
            continue
        p.write_text(text if "<item" in text else "", encoding="utf-8")
        return text if "<item" in text else ""
    return ""


def parse(text: str) -> tuple[str | None, date | None]:
    """응답 → (종목명, 마지막 거래일). 없는 코드면 (None, None)."""
    name, last = _NAME.search(text), _LAST.findall(text)
    if not name or not last:
        return None, None
    return name.group(1).strip(), datetime.strptime(last[-1], "%Y%m%d").date()


def candidates(stock_code: str) -> list[str]:
    return [stock_code[:5] + t for t in CANDIDATE_TAILS if stock_code[:5] + t != stock_code]


def rows(companies: list[dict], get=fetch, workers: int = 1) -> list[dict]:
    pairs = [(c, code) for c in companies if c["stock_code"] and len(c["stock_code"]) == 6 for code in candidates(c["stock_code"])]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        texts = list(pool.map(lambda pc: get(pc[1]), pairs))
    found = []
    for (c, code), text in zip(pairs, texts):
        name, last = parse(text)
        if name and _PREFERRED.match(name):
            found.append({"corp_code": c["corp_code"], "pref_code": code, "pref_name": name, "last_trade_date": last, "source": SOURCE})
    newest = max((r["last_trade_date"] for r in found), default=None)
    for r in found:
        r["status"] = LISTED if newest and (newest - r["last_trade_date"]).days <= LISTED_DAYS else GONE
    return found


def company_update(found: list[dict], corp_codes: list[str]) -> list[tuple]:
    """회사마다 (상장 우선주 코드 목록, 상태). 상장 중인 것만 코드로 적는다."""
    by: dict[str, list[dict]] = {}
    for r in found:
        by.setdefault(r["corp_code"], []).append(r)
    out = []
    for code in corp_codes:
        live = [r for r in by.get(code, []) if r["status"] == LISTED]
        if live:
            out.append((", ".join(f"{r['pref_code']} {r['pref_name']}" for r in live), f"상장 우선주 {len(live)}종목", code))
        elif by.get(code):
            out.append((None, "상장 우선주 없음 (예전 우선주는 거래 없음)", code))
        else:
            out.append((None, "상장 우선주 없음", code))
    return out


def main(url: str) -> None:
    with db.connect(url) as conn:
        companies = db.fetch_dicts(conn, "SELECT corp_code, corp_name, stock_code FROM core.core_company ORDER BY corp_code")
    found = rows(companies, workers=WORKERS)  # DB 연결 밖에서
    with db.connect(url) as conn:
        db.apply_schema(conn)
        n = db.replace_rows(conn, "raw.krx_pref_stock", found)
        with conn.cursor() as cur:
            cur.executemany("UPDATE core.core_company SET pref_stock_codes = %s, pref_status = %s WHERE corp_code = %s",
                            company_update(found, [c["corp_code"] for c in companies]))
        live = sum(r["status"] == LISTED for r in found)
        firms = len({r["corp_code"] for r in found if r["status"] == LISTED})
    print(f"raw.krx_pref_stock {n}행 · 상장 중 우선주 {live}종목 ({firms}곳) · core.core_company 우선주 칸 고침")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="고배당기업 상장 우선주 목록")
    ap.add_argument("--url", default=db.database_url())
    main(ap.parse_args().url)
