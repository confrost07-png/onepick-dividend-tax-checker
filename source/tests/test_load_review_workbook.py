"""검토본 반영: 정정 메모의 원문 값, 오타 칸, 원문 대조 우선순위."""
import pandas as pd
import pytest

from scripts import load_review_workbook as lr

FIN_COLS = ["회사명", "corp_code", "사업연도", "지배주주 순이익 분석 값(원)", "부채총계 분석 값(원)", "자본총계 분석 값(원)",
            "검토 상태", "검토자", "메모"]


def _book(tmp_path, rows):
    path = tmp_path / "검토본.xlsx"
    with pd.ExcelWriter(path) as w:
        pd.DataFrame(rows, columns=FIN_COLS).to_excel(w, sheet_name="02_재무", index=False)
    return path


def test_corrected_row_takes_source_value_from_memo(tmp_path):
    memo = "[원문 확인·DB 수정 필요] 부채총계 19,870,811,579→원문 21,824,472,744 / 지배주주 순이익 -2,179,240,729→원문 -37,787,144,555"
    path = _book(tmp_path, [["휴엠앤씨", "1185566", 2020, "--2179240729", 19870811579, 407512865, "정정됨(배제)", "조진영", memo],
                            ["가", "00000001", 2024, 10, None, 30, "확인완료", "박예지", None]])
    got = {(r["corp_code"], r["item"]): r["value_won"] for r in lr.financial_rows(path)}
    assert got[("01185566", "ni_owner_won")] == -37_787_144_555  # 숫자 아닌 칸이어도 메모의 원문 값을 씀
    assert got[("01185566", "liabilities_won")] == 21_824_472_744
    assert got[("01185566", "equity_won")] == 407_512_865  # 메모에 없는 칸은 분석 값
    assert got[("00000001", "liabilities_won")] is None  # 빈칸도 확정 값(원문에도 없음)


def test_non_number_without_memo_value_stops(tmp_path):
    path = _book(tmp_path, [["가", "00000001", 2024, "ㅋㅁㅁ", 1, 2, "확인완료", "박예지", None]])
    with pytest.raises(ValueError, match="숫자가 아님"):
        lr.financial_rows(path)


def test_source_check_wins_over_review_value():
    row = lambda v, src: lr.review("financial", "00000001", 2024, "ni_owner_won", v, "확인완료", None, None, src)  # noqa: E731
    merged = lr.merge([row(419_217_662_077, "검토본.xlsx"), row(21_751_670_000, "재무_원문대조.csv")])
    assert len(merged) == 1 and merged[0]["value_won"] == 21_751_670_000


def test_source_check_file_is_well_formed():
    rows = lr.source_check_rows(lr.DEFAULT_CHECK)
    assert rows and all(r["item"] in ("ni_owner_won", "liabilities_won", "equity_won") for r in rows)
    assert all(len(r["corp_code"]) == 8 for r in rows)


def test_later_source_check_file_covers_dividend_cells():
    rows = lr.source_check_rows(lr.DEFAULT_CHECKS[1])
    assert {r["target"] for r in rows if r["item"] == "d_dart_won"} == {"dividend"}
    assert {r["target"] for r in rows if r["item"] == "ni_owner_won"} == {"financial"}
    ilyang = next(r for r in rows if r["corp_code"] == "00146454")
    assert ilyang["value_won"] == 2_249_158_200 and ilyang["status"] == "원문 대조"
