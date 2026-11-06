"""분석 DB(PostgreSQL onepick)를 DuckDB 파일 하나로 내보낸다. 제출·공유용이면서 PostgreSQL 복구 파일.

- PostgreSQL의 raw(원천)·ref(세율표)·core(검증·확정)·partner(대조군) 표를 모두 같은 이름으로 옮긴다.
  보기(v_*_verified 같은 검증 값 보기, partner.v_panel)도 지금 값 그대로 표로 굳혀 넣는다(DuckDB만으로 읽을 수 있게).
- 값은 잃지 않게 옮긴다: numeric은 열마다 실제 값의 소수 자리수를 세어 DECIMAL(38, 자리수)로, 시간대 있는 시각은 UTC로.
- 복구에 필요한 것을 함께 넣는다(scripts.restore_duckdb가 읽음):
  main._ddl     = pg_dump --schema-only 결과(표·보기·기본키·외래키·인덱스·주석을 만드는 SQL)
  main._columns = 열마다 PostgreSQL 자료형과 DuckDB 자료형
  main._about   = 표마다 행 수·확인값(체크섬)·만든 때·git 커밋
  확인값은 행마다 값을 글자로 바꿔 md5를 더한 것이라 행 순서와 상관없다(numeric은 trim_scale, 시각은 UTC로 맞춰 셈).

연결 주소는 core.db와 같다: 환경변수 DATABASE_URL, 없으면 postgresql://localhost/onepick.
처음 한 번: pip install duckdb

사용: python -m scripts.export_duckdb [저장할 파일]   (기본: data/db/onepick_YYYYMMDD.duckdb)
"""
import argparse
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from psycopg import sql

from core import db
from scripts.export_db import git_commit, pg_tool

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ("raw", "ref", "core", "partner")  # ERD(source/scripts/report_erd_pdf.py)와 같은 범위

# PostgreSQL 자료형 → DuckDB 자료형. numeric은 열마다 자리수를 따로 정하고, 목록에 없는 것은 글자(VARCHAR)로 옮긴다
TYPES = {
    "smallint": "SMALLINT", "integer": "INTEGER", "bigint": "BIGINT",
    "real": "REAL", "double precision": "DOUBLE",
    "boolean": "BOOLEAN", "date": "DATE",
    "timestamp without time zone": "TIMESTAMP", "timestamp with time zone": "TIMESTAMP",  # UTC로 바꿔 옮김
    "json": "JSON", "jsonb": "JSON", "ARRAY": "JSON",  # 배열은 JSON 글자로
}


def objects(conn) -> list[tuple[str, str, str]]:
    """(스키마, 이름, 'table'·'view') — 표 먼저, 그다음 보기. 이름순."""
    rows = conn.execute(
        "select table_schema, table_name, case table_type when 'VIEW' then 'view' else 'table' end "
        "from information_schema.tables where table_schema = any(%s) order by 3, 1, 2", (list(SCHEMAS),)).fetchall()
    return [tuple(r) for r in rows]


def columns(conn, schema: str, name: str) -> list[tuple[str, str, str]]:
    """(열 이름, information_schema 자료형, format_type 자료형 — 복구할 때 그대로 쓰는 이름)."""
    return [tuple(r) for r in conn.execute(
        "select a.attname, c.data_type, format_type(a.atttypid, a.atttypmod) "
        "from pg_attribute a join pg_class t on t.oid = a.attrelid join pg_namespace n on n.oid = t.relnamespace "
        "join information_schema.columns c on c.table_schema = n.nspname and c.table_name = t.relname and c.column_name = a.attname "
        "where n.nspname = %s and t.relname = %s and a.attnum > 0 and not a.attisdropped order by a.attnum",
        (schema, name)).fetchall()]


def numeric_type(conn, schema: str, name: str, col: str) -> str:
    """값을 잃지 않는 DuckDB DECIMAL. 정수 자리 + 소수 자리가 38을 넘으면 글자로 옮긴다."""
    q = sql.SQL("select coalesce(max(scale(trim_scale({c}))), 0), coalesce(max(length(trunc(abs({c}))::text)), 1) "
                "from {s}.{t}").format(c=sql.Identifier(col), s=sql.Identifier(schema), t=sql.Identifier(name))
    scale, digits = conn.execute(q).fetchone()
    return f"DECIMAL(38,{scale})" if scale + digits <= 38 else "VARCHAR"


def duck_types(conn, schema: str, name: str, cols) -> dict[str, str]:
    return {c: numeric_type(conn, schema, name, c) if t == "numeric" else TYPES.get(t, "VARCHAR") for c, t, _ in cols}


def checksum_sql(schema: str, name: str, cols) -> sql.Composed:
    """(행 수, 확인값). 같은 값이면 행 순서와 numeric 소수 끝 0, 세션 시간대와 상관없이 같은 확인값이 나온다."""
    parts = []
    for col, typ, _ in cols:
        c = sql.Identifier(col)
        if typ == "numeric":
            parts.append(sql.SQL("trim_scale({})").format(c))
        elif typ == "timestamp with time zone":
            parts.append(sql.SQL("({} at time zone 'UTC')").format(c))
        else:
            parts.append(c)
    row = sql.SQL("row({})::text").format(sql.SQL(", ").join(parts))
    return sql.SQL("select count(*), coalesce(sum(('x' || substr(md5({row}), 1, 15))::bit(60)::bigint), 0)::text "
                   "from {s}.{t}").format(row=row, s=sql.Identifier(schema), t=sql.Identifier(name))


def select_sql(schema: str, name: str, cols) -> sql.Composed:
    """CSV로 뽑을 SELECT. 배열·JSON은 JSON 글자로, 시간대 있는 시각은 UTC 시각으로 바꾼다."""
    parts = []
    for col, typ, _ in cols:
        c = sql.Identifier(col)
        if typ == "ARRAY":
            parts.append(sql.SQL("to_json({})::text").format(c))
        elif typ in ("json", "jsonb"):
            parts.append(sql.SQL("{}::text").format(c))
        elif typ == "timestamp with time zone":
            parts.append(sql.SQL("({} at time zone 'UTC')").format(c))
        else:
            parts.append(c)
    return sql.SQL("select {} from {}.{}").format(sql.SQL(", ").join(parts), sql.Identifier(schema), sql.Identifier(name))


def copy_one(pg, duck, schema: str, name: str, tmp: Path) -> tuple[int, str, list]:
    cols = columns(pg, schema, name)
    types = duck_types(pg, schema, name, cols)
    csv = tmp / f"{schema}.{name}.csv"
    with pg.cursor() as cur, open(csv, "wb") as f:
        query = sql.SQL("copy ({}) to stdout with (format csv, header true)").format(select_sql(schema, name, cols))
        with cur.copy(query) as copy:
            for chunk in copy:
                f.write(chunk)
    ddl = ", ".join(f'"{c}" {types[c]}' for c, _, _ in cols)
    duck.execute(f'create or replace table "{schema}"."{name}" ({ddl})')
    # CSV의 빈 칸(따옴표 없음)은 NULL, 따옴표 친 빈 글자("")는 빈 글자로 둔다(PostgreSQL CSV 규칙과 같게)
    # 형식은 PostgreSQL CSV로 정해져 있으니 짐작(auto_detect)하지 않는다: 짐작하면 앞부분만 보고 숫자 열로 오해해 멈춘다(DuckDB 2)
    duck.execute(f'insert into "{schema}"."{name}" select * from read_csv(?, header = true, columns = ?, '
                 f'auto_detect = false, delim = \',\', quote = \'"\', escape = \'"\', '
                 f'allow_quoted_nulls = false, max_line_size = 100000000)', [csv.as_posix(), types])
    csv.unlink()
    n = duck.execute(f'select count(*) from "{schema}"."{name}"').fetchone()[0]
    expected, check = pg.execute(checksum_sql(schema, name, cols)).fetchone()
    if n != expected:  # 옮기다 빠진 행이 있으면 멈춘다
        sys.exit(f"{schema}.{name}: PostgreSQL {expected:,}행인데 DuckDB에는 {n:,}행이에요. 다시 실행해 주세요.")
    return n, check, [(schema, name, i, c, pgt, types[c]) for i, (c, _, pgt) in enumerate(cols, 1)]


def schema_ddl(pg, url: str) -> str:
    """표·보기·제약·인덱스·주석을 만드는 SQL. 소유자·권한은 빼서 받는 쪽 사용자 이름이 달라도 된다.
    확장(pg_trgm 등)은 public 스키마에 있어 스키마를 골라 뽑으면 빠지므로 맨 앞에 따로 붙인다."""
    exts = pg.execute("select e.extname, n.nspname from pg_extension e join pg_namespace n on n.oid = e.extnamespace "
                      "where e.extname <> 'plpgsql' order by 1").fetchall()
    head = "".join(f'CREATE EXTENSION IF NOT EXISTS "{e}" WITH SCHEMA "{n}";\n' for e, n in exts)
    args = [pg_tool("pg_dump"), "--schema-only", "--no-owner", "--no-privileges", "-d", url]
    for s in SCHEMAS:
        args += ["-n", s]
    return head + subprocess.run(args, check=True, capture_output=True, text=True).stdout


def main() -> None:
    try:
        import duckdb
    except ImportError:
        sys.exit("duckdb가 없어요. 먼저 설치해 주세요:  python -m pip install duckdb")

    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?", help="저장할 .duckdb 파일 (기본: data/db/onepick_오늘날짜.duckdb)")
    args = ap.parse_args()
    out = Path(args.out) if args.out else ROOT / "data" / "db" / f"onepick_{datetime.now():%Y%m%d}.duckdb"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()  # 같은 날 다시 만들면 새로 만든다

    url = db.database_url()
    print(f"읽는 곳: {url.split('@')[-1]}\n저장할 곳: {out}")
    done, cols_meta = [], []
    with db.connect(url) as pg, duckdb.connect(str(out)) as duck, tempfile.TemporaryDirectory() as tmp:
        for schema in SCHEMAS:
            duck.execute(f'create schema if not exists "{schema}"')
        items = objects(pg)
        if not items:
            sys.exit("옮길 표가 없어요. DB 복원(scripts.restore_db)이 끝났는지 확인해 주세요.")
        for i, (schema, name, kind) in enumerate(items, 1):
            n, check, meta = copy_one(pg, duck, schema, name, Path(tmp))
            done.append((schema, name, kind, n, check))
            cols_meta += meta
            print(f"  [{i}/{len(items)}] {schema}.{name}{' (보기→표)' if kind == 'view' else ''}: {n:,}행")
        pg_version = pg.execute("show server_version").fetchone()[0]
        now, commit = datetime.now().replace(microsecond=0), git_commit()
        duck.execute("create or replace table main._about (schema_name varchar, table_name varchar, source_kind varchar, "
                     "row_count bigint, checksum varchar, exported_at timestamp, source varchar, git_commit varchar)")
        duck.executemany("insert into main._about values (?, ?, ?, ?, ?, ?, ?, ?)",
                         [(s, t, k, n, c, now, f"PostgreSQL {pg_version} onepick", commit) for s, t, k, n, c in done])
        duck.execute("create or replace table main._columns (schema_name varchar, table_name varchar, ordinal integer, "
                     "column_name varchar, pg_type varchar, duck_type varchar)")
        duck.executemany("insert into main._columns values (?, ?, ?, ?, ?, ?)", cols_meta)
        duck.execute("create or replace table main._ddl (made_at timestamp, pg_version varchar, sql varchar)")
        duck.execute("insert into main._ddl values (?, ?, ?)", [now, pg_version, schema_ddl(pg, url)])
    tables = sum(1 for x in done if x[2] == "table")
    print(f"\n끝! 표 {tables}개 + 보기 {len(done) - tables}개를 옮겼어요 → {out} ({out.stat().st_size / 1e6:.1f}MB)")
    print("PostgreSQL로 되살리기: python -m scripts.restore_duckdb " + str(out))


if __name__ == "__main__":
    main()
