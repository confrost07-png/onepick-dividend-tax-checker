"""회사 행동 분석(금리·환율 노출도, 분리과세 이중차분) 결과 저장·읽기 (core.core_behavior_fit, core.core_behavior_series).

계산은 source/scripts/analyze_exposure_dividend.py, source/scripts/analyze_policy_did.py가 하고, 화면은 저장한 값만 읽는다.
분석마다 자기 줄만 지우고 다시 넣는다(다른 분석 줄은 그대로).
"""
from dataclasses import dataclass
import math

import psycopg

from core import db

FIT_COLS = ["analysis", "name", "role", "coef", "low", "high", "p_cluster", "p_perm", "p_holm", "n", "n_firms", "n_treated"]
SERIES_COLS = ["analysis", "series", "label", "year", "value", "low", "high", "n"]


def _clean(v):
    """numpy 값은 파이썬 값으로, NaN은 NULL로."""
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, float) and math.isnan(v):
        return None
    return v


def save(conn: psycopg.Connection, analysis: str, fits: list[dict], series: list[dict]) -> tuple[int, int]:
    for table, cols, rows in [("core_behavior_fit", FIT_COLS, fits), ("core_behavior_series", SERIES_COLS, series)]:
        conn.execute(f"DELETE FROM core.{table} WHERE analysis = %s", (analysis,))
        with conn.cursor() as cur:
            cur.executemany(
                f"INSERT INTO core.{table} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})",
                [[_clean({**r, 'analysis': analysis}.get(c)) for c in cols] for r in rows])
    return len(fits), len(series)


@dataclass(frozen=True)
class Behavior:
    fits: list[dict]
    series: list[dict]
    built_at: str


def load(url: str | None = None) -> Behavior | None:
    """표가 없거나 비었으면 None (화면은 그 부분을 숨긴다)."""
    try:
        with db.connect(url) as conn:
            fits = db.fetch_dicts(conn, f"SELECT {', '.join(FIT_COLS)}, built_at FROM core.core_behavior_fit ORDER BY analysis, role, name")
            series = db.fetch_dicts(conn, f"SELECT {', '.join(SERIES_COLS)} FROM core.core_behavior_series ORDER BY analysis, series, label, year")
    except (psycopg.OperationalError, psycopg.errors.UndefinedTable):
        return None
    if not fits:
        return None
    built = max(f.pop("built_at") for f in fits).strftime("%Y-%m-%d")
    return Behavior(fits, series, built)
