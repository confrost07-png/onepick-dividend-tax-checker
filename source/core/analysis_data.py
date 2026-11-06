"""S-01 데이터 분석 화면이 읽는 이벤트 스터디 결과 (onepick DB: core.core_event_summary, core.core_event_curve).

화면에는 시장지수를 확인한 기간(2025년까지)의 집계만 보낸다. 2026년(지수 미검증) 결과는 읽지 않는다.
DB에 연결할 수 없거나 결과 표가 비어 있으면 None을 돌려주고, 화면은 예시 화면으로 대신한다.
"""
from dataclasses import dataclass

import pandas as pd
import psycopg

from core import db
from core.event_study import VERIFIED


@dataclass(frozen=True)
class Results:
    summary: pd.DataFrame  # kind, window_days, basis, return_type, sample, n_cases, median_pct, p25_pct, p75_pct, shown, n_excluded
    curve: pd.DataFrame    # kind, window_days, basis, return_type, sample, day, n_cases, median_pct, p25_pct, p75_pct
    built_at: str


def load(url: str | None = None) -> Results | None:
    try:
        with db.connect(url) as conn:
            summary = db.fetch_dicts(conn, """
                SELECT kind, window_days, basis, return_type, sample, n_cases, median_pct::float, p25_pct::float,
                       p75_pct::float, shown, n_excluded, built_at
                FROM core.core_event_summary WHERE period = %s""", (VERIFIED,))
            curve = db.fetch_dicts(conn, """
                SELECT kind, window_days, basis, return_type, sample, day, n_cases, median_pct::float, p25_pct::float,
                       p75_pct::float
                FROM core.core_event_curve WHERE period = %s ORDER BY kind, window_days, basis, return_type, sample, day""",
                (VERIFIED,))
    except (psycopg.OperationalError, psycopg.errors.UndefinedTable):
        return None
    if not summary:
        return None
    built = max(r.pop("built_at") for r in summary)
    return Results(pd.DataFrame(summary), pd.DataFrame(curve), built.strftime("%Y-%m-%d"))
