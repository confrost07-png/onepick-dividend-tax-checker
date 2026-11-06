"""PostgreSQL 연결과 적재 도우미 (PRD v0.2 테이블, source/db/schema.sql).

연결 주소는 환경변수 DATABASE_URL, 없으면 이 컴퓨터의 onepick DB.
"""
import os
from pathlib import Path

import psycopg
from psycopg import sql

DEFAULT_URL = "postgresql://localhost/onepick"
SCHEMA_FILE = Path(__file__).resolve().parents[2] / "source" / "db" / "schema.sql"


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_URL)


def connect(url: str | None = None) -> psycopg.Connection:
    return psycopg.connect(url or database_url())


def create_database(url: str | None = None) -> bool:
    """url이 가리키는 DB가 없으면 만든다. 만들었으면 True."""
    info = psycopg.conninfo.conninfo_to_dict(url or database_url())
    name = info.pop("dbname")
    info["dbname"] = "postgres"
    with psycopg.connect(**info, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone()
        if exists:
            return False
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        return True


def apply_schema(conn: psycopg.Connection) -> None:
    conn.execute(SCHEMA_FILE.read_text(encoding="utf-8"))


def replace_rows(conn: psycopg.Connection, table: str, rows: list[dict]) -> int:
    """table(예: 'raw.dart_financial')의 행을 모두 rows로 바꾼다. 원천에서 다시 만들 수 있는 표에만 쓴다."""
    schema, name = table.split(".")
    target = sql.Identifier(schema, name)
    conn.execute(sql.SQL("TRUNCATE {} CASCADE").format(target))
    if not rows:
        return 0
    cols = list(rows[0])
    copy = sql.SQL("COPY {} ({}) FROM STDIN").format(target, sql.SQL(", ").join(map(sql.Identifier, cols)))
    with conn.cursor().copy(copy) as cp:
        for r in rows:
            cp.write_row([r[c] for c in cols])
    return len(rows)


def fetch_dicts(conn: psycopg.Connection, query: str, params=None) -> list[dict]:
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(query, params)
        return cur.fetchall()


def copy_rows(conn: psycopg.Connection, table: str, cols: list[str], rows) -> int:
    """rows(열 이름 → 값 dict를 하나씩 내는 것)를 COPY로 넣는다. 수백만 행도 메모리에 다 올리지 않는다. 비우지는 않음."""
    schema, name = table.split(".")
    copy = sql.SQL("COPY {} ({}) FROM STDIN").format(sql.Identifier(schema, name), sql.SQL(", ").join(map(sql.Identifier, cols)))
    n = 0
    with conn.cursor().copy(copy) as cp:
        for r in rows:
            cp.write_row([r.get(c) for c in cols])
            n += 1
    return n
