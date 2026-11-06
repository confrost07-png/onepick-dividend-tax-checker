"""onepick DB 전체를 다른 사람에게 넘길 파일로 뽑는다 → data/db/onepick_YYYYMMDD.dump + .json.

실행: .venv/bin/python -m scripts.export_db [--url ...] [--out data/db/onepick_20261029.dump]
- 덤프: pg_dump 사용자 지정 형식(-Fc, 압축). 소유자·권한은 빼서 받는 쪽 사용자 이름이 달라도 된다.
- 확인표(.json): 표마다 행 수, 판정 집계, 파일 SHA-256, git 커밋. 되살린 쪽에서 scripts.restore_db가 대조한다.
덤프 파일은 git에 넣지 않는다(.gitignore). 드라이브·메신저로 직접 전달한다.
"""
import argparse
import glob
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

from core import db

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ("raw", "core", "ref", "partner")  # 행 수를 대조할 범위 (덤프 자체는 DB 전체)


def pg_tool(name: str) -> str:
    """PATH에 있으면 그것, 없으면 맥 Postgres.app·Homebrew, 윈도우 공식 설치본에서 찾는다."""
    candidates = [
        f"/Applications/Postgres.app/Contents/Versions/latest/bin/{name}",
        *sorted(glob.glob(rf"C:\Program Files\PostgreSQL\*\bin\{name}.exe"), reverse=True),
        f"/opt/homebrew/bin/{name}",
        f"/usr/local/bin/{name}",
    ]
    found = shutil.which(name) or next((c for c in candidates if Path(c).exists()), None)
    if found is None:
        sys.exit(f"{name}을 찾지 못했어요. PostgreSQL 17을 설치한 뒤 다시 실행해 주세요 (report/실행안내/팀원_실행_안내.md).")
    return found


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def snapshot(url: str) -> dict:
    """표마다 행 수, 뷰 수, 판정 집계. 뽑을 때와 되살린 뒤를 같은 방법으로 센다."""
    with db.connect(url) as conn:
        names = [r[0] for r in conn.execute(
            "SELECT table_schema || '.' || table_name FROM information_schema.tables "
            "WHERE table_schema = ANY(%s) AND table_type = 'BASE TABLE' ORDER BY 1", (list(SCHEMAS),))]
        tables = {n: conn.execute(f"SELECT count(*) FROM {n}").fetchone()[0] for n in names}
        views = conn.execute("SELECT count(*) FROM information_schema.views WHERE table_schema = ANY(%s)",
                             (list(SCHEMAS),)).fetchone()[0]
        judgement = dict(conn.execute(
            "SELECT status, count(*) FROM core.core_judgement_2026 GROUP BY 1 ORDER BY 1").fetchall())
        server = conn.execute("SHOW server_version").fetchone()[0]
    return {"tables": tables, "views": views, "judgement": judgement, "server_version": server}


def git_commit() -> str | None:
    r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    return r.stdout.strip() or None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=db.database_url())
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "db" / f"onepick_{date.today():%Y%m%d}.dump")
    args = ap.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([pg_tool("pg_dump"), "-Fc", "--no-owner", "--no-privileges", "-d", args.url, "-f", str(args.out)],
                   check=True)
    info = snapshot(args.url)
    manifest = {"dump": args.out.name, "made": date.today().isoformat(), "sha256": sha256(args.out),
                "git_commit": git_commit(), **info}
    manifest_path = args.out.with_suffix(".json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")

    size_mb = args.out.stat().st_size / 1_000_000
    print(f"덤프: {args.out} ({size_mb:.1f}MB)")
    print(f"확인표: {manifest_path}")
    print(f"표 {len(info['tables'])}개 · 뷰 {info['views']}개 · 판정 {info['judgement']} · PostgreSQL {info['server_version']}")


if __name__ == "__main__":
    main()
