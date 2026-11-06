"""4조 대조군 상장사 수정 종가 → partner.krx_price_daily (네이버 금융 차트 공개 자료).

실행: .venv/bin/python -m scripts.collect_partner_prices [--limit N] [--url ...]
- 대상: partner.company 중 grp = '대조군', 지금 상장(유가증권·코스닥·코넥스), 종목코드 있음. 상장폐지·비상장 회사는 받을 수 없어 뺀다.
- 원천: fchart.stock.naver.com 일봉 (수정주가). 우리 638사 KRX 수정 종가(data/raw/krx/prices.csv, pykrx)와
  8개사 표본에서 모든 거래일 값이 같았다 (2026-11-02 확인).
- 받은 응답은 data/raw/naver_fchart/{종목코드}.txt에 두고 다시 받지 않는다 (git 제외). 2018-01-02 이후만 넣는다.
- 다시 돌리면 partner.krx_price_daily를 비우고 새로 채운다.
"""
import argparse
import re
import time
import urllib.request
from datetime import date
from pathlib import Path

from core import db

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "raw" / "naver_fchart"
URL = "https://fchart.stock.naver.com/sise.nhn?symbol={}&timeframe=day&count=2600&requestType=0"
START = date(2018, 1, 2)  # 우리 KRX 주가 파일 시작일
SOURCE = "네이버 금융 차트(fchart) 일봉 수정주가"
MARKETS = ("유가증권", "코스닥", "코넥스")
_ROW = re.compile(r'data="(\d{8})\|([\d.]*)\|([\d.]*)\|([\d.]*)\|([\d.]*)\|(\d*)"')


def parse(text: str) -> list[tuple[date, float, int]]:
    """fchart 응답 → (거래일, 수정 종가, 거래량). 종가가 비거나 0인 줄은 뺀다."""
    out = []
    for d, _o, _h, _l, close, vol in _ROW.findall(text):
        if close and float(close) > 0:
            out.append((date(int(d[:4]), int(d[4:6]), int(d[6:])), float(close), int(vol or 0)))
    return out


def fetch(code: str, pause: float = 0.25) -> str:
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"{code}.txt"
    if p.exists():
        return p.read_text(encoding="utf-8")
    for wait in (0, 2, 10, 30):
        time.sleep(wait or pause)
        try:
            text = urllib.request.urlopen(URL.format(code), timeout=30).read().decode("euc-kr", "replace")
        except OSError:
            continue
        if "<item" in text or "<chartdata" in text:
            p.write_text(text, encoding="utf-8")
            return text
    return ""


def targets(conn) -> list[dict]:
    return db.fetch_dicts(conn, """SELECT corp_code, corp_name, stock_code, market FROM partner.company
                                   WHERE grp = '대조군' AND listed_now = 'Y' AND market = ANY(%s) AND stock_code ~ '^[0-9A-Z]{6}$'
                                   ORDER BY corp_code""", (list(MARKETS),))


def rows_for(t: dict, text: str):
    for d, close, vol in parse(text):
        if d >= START:
            yield {"corp_code": t["corp_code"], "trade_date": d, "close_adj": close, "volume": vol, "source": SOURCE}


def collect(url: str, limit: int | None = None) -> dict:
    with db.connect(url) as conn:
        db.apply_schema(conn)
        ts = targets(conn)[:limit] if limit else targets(conn)
        got, empty, n = 0, [], 0
        conn.execute("TRUNCATE partner.krx_price_daily")

        def gen():
            nonlocal got, n
            for i, t in enumerate(ts, 1):
                text = fetch(t["stock_code"])
                rs = list(rows_for(t, text))
                if rs:
                    got += 1
                    n += len(rs)
                    yield from rs
                else:
                    empty.append(t["corp_name"])
                if i % 100 == 0:
                    print(f"  {i}/{len(ts)}", flush=True)

        db.copy_rows(conn, "partner.krx_price_daily", ["corp_code", "trade_date", "close_adj", "volume", "source"], gen())
    print(f"  대상 {len(ts):,}사 · 주가 받음 {got:,}사 · {n:,}행 · 못 받음 {len(empty)}사 {empty[:10]}")
    return {"targets": len(ts), "got": got, "rows": n, "empty": empty}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="4조 대조군 상장사 수정 종가 → partner.krx_price_daily")
    ap.add_argument("--limit", type=int, help="앞에서 N곳만 (시험용)")
    ap.add_argument("--url", default=db.database_url())
    a = ap.parse_args()
    collect(a.url, a.limit)
