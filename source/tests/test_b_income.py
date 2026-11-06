"""B(배당소득) 규칙: KIND 공시 값 우선, 감액배당 메모가 있으면 B(2025)는 비우고 보류."""
from core import b_income as bi

KIND = {"b2024_won": 100, "prev_year": "2025", "prev_d_won": 120, "prevprev_d_won": 100, "reduction_note": None}


def test_kind_values_are_used_in_won():
    b = bi.b_year(KIND, dart_d2025=118_000_000, dart_d2024=99_000_000, stock_div_2025=5)
    assert (b.b2024, b.d2025, b.d2024, b.d_unit, b.d_source) == (100, 120, 100, 1, bi.KIND)
    assert b.b2025 == 125 and b.b2025_source == bi.B2025_OK  # 주식배당을 더함


def test_reduction_note_holds_b2025():
    b = bi.b_year({**KIND, "reduction_note": "기말배당금 중 50%는 자본준비금을 감액하여 지급"}, None, None)
    assert b.b2025 is None and b.reduction_unconfirmed and b.b2025_source == bi.B2025_HOLD


def test_without_kind_falls_back_to_dart_and_source_value():
    b = bi.b_year(None, dart_d2025=3_000_000, dart_d2024=2_000_000, b2024_from_source=5_421_402_000)
    assert (b.d2025, b.d_unit, b.d_source) == (3_000_000, bi.MIL, bi.DART_D)
    assert b.b2024 == 5_421_402_000 and "DB 빈칸" in b.b2024_source and b.b2025 == 3_000_000
