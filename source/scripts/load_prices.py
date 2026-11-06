"""KRX 수정 종가·시장지수·빈칸 사유 → onepick DB, 그리고 날짜별 사용 등급(source/core/price_quality.py).

실행: .venv/bin/python -m scripts.load_prices [--prices 경로] [--market 경로] [--status 경로] [--targets 경로] [--url ...]
자료는 한국거래소(KRX) 시세를 pykrx로 받은 것이다. 알려진 문제와 다시 넣는 법 → report/검증/데이터_교체_예정.md
다시 돌리면 표를 비우고 새로 채운다. 주지 않은 파일의 표는 건드리지 않는다.
원본 표(raw.krx_*)는 고치지 않고, 문제 있는 날은 core.core_price_flag·core.core_index_flag에 표시만 한다.
"""
import argparse
from pathlib import Path

from core import db
from core import price_quality as pq
from core.raw_tables import KRX_DIR, krx_day_status, krx_market_index, krx_prices, read_krx, read_krx_table


def load_prices(url: str, prices: Path, market: Path | None = None,
                status: Path | None = None, targets: Path | None = None) -> dict[str, int]:
    counts = {}
    price_wide = read_krx(prices)
    with db.connect(url) as conn:
        db.apply_schema(conn)
        counts["raw.krx_price_daily"] = db.replace_rows(conn, "raw.krx_price_daily", krx_prices(price_wide, prices.name))
        counts["core.core_price_flag"] = db.replace_rows(conn, "core.core_price_flag", pq.price_flags(price_wide))
        if market is not None:
            market_wide = read_krx(market)
            counts["raw.krx_market_index"] = db.replace_rows(conn, "raw.krx_market_index",
                                                             krx_market_index(market_wide, market.name))
            counts["core.core_index_flag"] = db.replace_rows(conn, "core.core_index_flag", pq.index_flags(market_wide))
        if status is not None and targets is not None:
            rows = krx_day_status(read_krx_table(status), read_krx_table(targets), status.name)
            counts["raw.krx_day_status"] = db.replace_rows(conn, "raw.krx_day_status", rows)
    for table, n in counts.items():
        print(f"  {table}: {n:,}행")
    return counts


def _default(path: Path) -> Path | None:
    return path if path.exists() else None


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="KRX 주가·지수·빈칸 사유를 onepick DB에 적재하고 사용 등급 표시")
    ap.add_argument("--prices", type=Path, default=KRX_DIR / "prices.csv", help="KRX prices.csv")
    ap.add_argument("--market", type=Path, default=_default(KRX_DIR / "market.csv"), help="KRX market.csv")
    ap.add_argument("--status", type=Path, default=_default(KRX_DIR / "일별상태.csv"), help="KRX 일별상태.csv")
    ap.add_argument("--targets", type=Path, default=_default(KRX_DIR / "대상목록.csv"), help="KRX 대상목록.csv")
    ap.add_argument("--url", default=db.database_url(), help="PostgreSQL 주소")
    args = ap.parse_args()
    load_prices(args.url, args.prices, args.market, args.status, args.targets)
