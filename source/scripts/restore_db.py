"""넘겨받은 덤프 파일로 onepick DB를 되살리고, 뽑을 때의 확인표(.json)와 행 수를 대조한다.

실행: .venv/bin/python -m scripts.restore_db [data/db/onepick_20261029.dump] [--url ...] [--replace]
- 덤프를 안 적으면 source/db/ 안의 가장 최근 onepick_*.dump를 쓴다.
- 확인표는 덤프와 같은 이름의 .json (scripts.export_db가 만든 것). 파일 SHA-256부터 맞는지 본다.
- 대상 DB가 이미 있으면 멈춘다. --replace면 지우고 다시 만든다(그 DB의 기존 내용은 사라짐).
- 표마다 행 수·뷰 수·판정 집계가 하나라도 다르면 실패로 끝낸다(종료 코드 1).
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import psycopg
from psycopg import sql

from core import db
from scripts.export_db import ROOT, pg_tool, sha256, snapshot


def drop_database(url: str) -> None:
    info = psycopg.conninfo.conninfo_to_dict(url)
    name = info.pop("dbname")
    info["dbname"] = "postgres"
    with psycopg.connect(**info, autocommit=True) as conn:
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


def latest_dump(folder: Path) -> Path | None:
    """이름에 날짜가 들어 있으니 이름순 마지막이 가장 최근 덤프."""
    return max(folder.glob("onepick_*.dump"), default=None)


def compare(expected: dict, got: dict) -> list[str]:
    """다른 곳을 한 줄씩. 같으면 빈 목록."""
    diffs = []
    for name in sorted(set(expected["tables"]) | set(got["tables"])):
        a, b = expected["tables"].get(name), got["tables"].get(name)
        if a != b:
            diffs.append(f"{name}: 뽑을 때 {a} → 되살린 뒤 {b}")
    for key in ("views", "judgement"):
        if expected[key] != got[key]:
            diffs.append(f"{key}: 뽑을 때 {expected[key]} → 되살린 뒤 {got[key]}")
    return diffs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dump", type=Path, nargs="?", help="덤프 파일 (기본: source/db/ 안의 가장 최근 onepick_*.dump)")
    ap.add_argument("--url", default=db.database_url())
    ap.add_argument("--replace", action="store_true", help="대상 DB가 있으면 지우고 다시 만든다")
    args = ap.parse_args()

    args.dump = args.dump or latest_dump(ROOT / "data" / "db")
    if not args.dump or not args.dump.exists():
        sys.exit("덤프 파일을 찾지 못했어요. source/db/ 폴더에 onepick_*.dump와 같은 이름의 .json이 있는지 확인해 주세요.")
    print(f"복원할 곳: {args.url}\n덤프: {args.dump.name}")

    manifest_path = args.dump.with_suffix(".json")
    if not manifest_path.exists():
        sys.exit(f"확인표가 없어요: {manifest_path} (덤프와 함께 받은 .json을 같은 폴더에 두세요)")
    expected = json.loads(manifest_path.read_text(encoding="utf-8"))
    if sha256(args.dump) != expected["sha256"]:
        sys.exit("덤프 파일이 확인표와 달라요(SHA-256 불일치). 파일을 다시 받아 주세요.")

    if args.replace:
        drop_database(args.url)
    if not db.create_database(args.url):
        sys.exit(f"DB가 이미 있어요: {args.url}\n지우고 다시 만들려면 --replace를 붙이세요.")
    subprocess.run([pg_tool("pg_restore"), "--no-owner", "--no-privileges", "--exit-on-error", "-d", args.url,
                    str(args.dump)], check=True)

    got = snapshot(args.url)
    diffs = compare(expected, got)
    if diffs:
        print("되살렸지만 뽑을 때와 다른 곳이 있어요:")
        print("\n".join(f"- {d}" for d in diffs))
        sys.exit(1)
    print(f"되살리기 완료: {args.url} (판정 회사 {sum(got['judgement'].values())}곳, 638곳이면 정상)")
    print(f"표 {len(got['tables'])}개 행 수 · 뷰 {got['views']}개 · 판정 {got['judgement']} 모두 뽑을 때와 같아요.")
    print(f"뽑은 날 {expected['made']}, 코드 커밋 {expected['git_commit']} (앱 코드도 이 커밋에 맞추세요)")


if __name__ == "__main__":
    main()
