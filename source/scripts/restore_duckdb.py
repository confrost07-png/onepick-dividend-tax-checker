"""scripts.export_duckdb가 만든 .duckdb 파일 하나로 PostgreSQL onepick DB를 되살리고, 뽑을 때와 같은지 대조한다.

실행: python -m scripts.restore_duckdb [data/db/onepick_20261103.duckdb] [--url ...] [--replace]
- 파일을 안 적으면 data/db/ 안의 가장 최근 onepick_*.duckdb를 쓴다.
- 순서: DB 만들기 → main._ddl(pg_dump --schema-only)로 표·보기·제약 만들기 → 표마다 DuckDB → CSV → COPY →
  표마다 행 수와 확인값(체크섬)을 main._about과 대조 → 판정 집계 출력.
- 보기는 DDL로 다시 만들어지므로 DuckDB에 굳혀 둔 보기 값은 넣지 않는다.
- 외래키는 다 넣은 뒤 지키면 되므로, 넣는 동안만 session_replication_role = replica로 순서 검사를 끈다(슈퍼유저 필요).
- 대상 DB가 이미 있으면 멈춘다. --replace면 지우고 다시 만든다(그 DB의 기존 내용은 사라짐).
- 하나라도 다르면 실패로 끝낸다(종료 코드 1).
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from psycopg import sql

from core import db
from scripts.export_db import pg_tool
from scripts.export_duckdb import ROOT, checksum_sql
from scripts.restore_db import drop_database


def latest(folder: Path) -> Path | None:
    """이름에 날짜가 들어 있으니 이름순 마지막이 가장 최근 파일."""
    return max(folder.glob("onepick_*.duckdb"), default=None)


def duck_select(schema: str, name: str, cols: list[tuple[str, str]]) -> str:
    """DuckDB에서 CSV로 뽑을 SELECT. 시각은 UTC 그대로, JSON은 글자로."""
    parts = [f'cast("{c}" as varchar)' if d == "JSON" else f'"{c}"' for c, d in cols]
    return f'select {", ".join(parts)} from "{schema}"."{name}"'


def main() -> None:
    try:
        import duckdb
    except ImportError:
        sys.exit("duckdb가 없어요. 먼저 설치해 주세요:  python -m pip install duckdb")

    ap = argparse.ArgumentParser()
    ap.add_argument("file", type=Path, nargs="?", help="되살릴 .duckdb (기본: data/db/ 안의 가장 최근 onepick_*.duckdb)")
    ap.add_argument("--url", default=db.database_url())
    ap.add_argument("--replace", action="store_true", help="대상 DB가 있으면 지우고 다시 만든다")
    args = ap.parse_args()

    src = args.file or latest(ROOT / "data" / "db")
    if not src or not src.exists():
        sys.exit("DuckDB 파일을 찾지 못했어요. data/db/ 폴더에 onepick_*.duckdb가 있는지 확인해 주세요.")
    duck = duckdb.connect(str(src), read_only=True)
    about = duck.execute("select schema_name, table_name, row_count, checksum, git_commit, exported_at "
                         "from main._about where source_kind = 'table' order by 1, 2").fetchall()
    ddl = duck.execute("select sql from main._ddl").fetchone()[0]
    cols = {}
    for s, t, c, d in duck.execute("select schema_name, table_name, column_name, duck_type from main._columns "
                                   "order by schema_name, table_name, ordinal").fetchall():
        cols.setdefault((s, t), []).append((c, d))
    print(f"되살릴 곳: {args.url.split('@')[-1]}\n파일: {src.name} (뽑은 때 {about[0][5]}, 코드 커밋 {about[0][4]})")

    if args.replace:
        drop_database(args.url)
    if not db.create_database(args.url):
        sys.exit(f"DB가 이미 있어요: {args.url}\n지우고 다시 만들려면 --replace를 붙이세요.")
    with tempfile.TemporaryDirectory() as tmp:
        ddl_file = Path(tmp) / "schema.sql"
        ddl_file.write_text(ddl, encoding="utf-8")
        subprocess.run([pg_tool("psql"), "-q", "-v", "ON_ERROR_STOP=1", "-d", args.url, "-f", str(ddl_file)],
                       check=True, stdout=subprocess.DEVNULL)

        diffs = []
        with db.connect(args.url) as pg:
            pg.execute("set session_replication_role = replica")
            pg.execute("set time zone 'UTC'")  # DuckDB에 UTC로 넣어 둔 시각을 UTC로 읽게
            for i, (s, t, n, check, _, _) in enumerate(about, 1):
                csv = Path(tmp) / f"{s}.{t}.csv"
                duck.execute(f"copy ({duck_select(s, t, cols[(s, t)])}) to '{csv.as_posix()}' (header, delimiter ',')")
                names = sql.SQL(", ").join(sql.Identifier(c) for c, _ in cols[(s, t)])
                with pg.cursor() as cur, open(csv, "rb") as f:
                    with cur.copy(sql.SQL("copy {}.{} ({}) from stdin with (format csv, header true)").format(
                            sql.Identifier(s), sql.Identifier(t), names)) as copy:
                        while chunk := f.read(1 << 20):
                            copy.write(chunk)
                csv.unlink()
                pg_cols = [tuple(r) for r in pg.execute(
                    "select column_name, data_type, '' from information_schema.columns "
                    "where table_schema = %s and table_name = %s order by ordinal_position", (s, t)).fetchall()]
                got_n, got_check = pg.execute(checksum_sql(s, t, pg_cols)).fetchone()
                ok = got_n == n and got_check == check
                if not ok:
                    diffs.append(f"{s}.{t}: 뽑을 때 {n:,}행·{check} → 되살린 뒤 {got_n:,}행·{got_check}")
                print(f"  [{i}/{len(about)}] {s}.{t}: {got_n:,}행 {'같음' if ok else '다름!'}")
            pg.execute("set session_replication_role = origin")
            pg.commit()
            pg.execute("analyze")
            judgement = dict(pg.execute("select status, count(*) from core.core_judgement_2026 group by 1 order by 1").fetchall())
            views = pg.execute("select count(*) from information_schema.views where table_schema in ('raw','ref','core','partner')").fetchone()[0]
    duck.close()
    if diffs:
        print("되살렸지만 뽑을 때와 다른 표가 있어요:")
        print("\n".join(f"- {d}" for d in diffs))
        sys.exit(1)
    print(f"\n되살리기 완료: 표 {len(about)}개 행 수·확인값 모두 같음, 보기 {views}개, 판정 {judgement}")
    print(f"코드 커밋 {about[0][4]}에 맞춰 앱을 실행하세요.")


if __name__ == "__main__":
    main()
