"""DuckDB 복구 파일: 확인값 SQL이 값만 보고(소수 끝 0·시간대와 상관없이), JSON은 글자로 옮기는지."""
from scripts.export_duckdb import checksum_sql
from scripts.restore_duckdb import duck_select


def test_checksum_normalizes_numeric_and_timestamptz():
    cols = [("amount", "numeric", ""), ("made_at", "timestamp with time zone", ""), ("name", "text", "")]
    q = checksum_sql("core", "t", cols).as_string(None)
    assert 'trim_scale("amount")' in q and """("made_at" at time zone 'UTC')""" in q and '"name"' in q
    assert q.startswith("select count(*)")


def test_duck_select_casts_json_to_text():
    q = duck_select("raw", "t", [("payload", "JSON"), ("n", "INTEGER")])
    assert q == 'select cast("payload" as varchar), "n" from "raw"."t"'
