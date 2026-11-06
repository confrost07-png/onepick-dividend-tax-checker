"""원천 엑셀(01~09) → raw 테이블 행. DB 없이 시험할 수 있게 DataFrame을 받아 dict 목록을 돌려준다.

값은 고치지 않고 열 이름만 바꾼다. 숫자 칸은 쉼표·공백을 걷어 내고 숫자로 읽되, '-'·빈칸은 비워 둔다.
"""
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

# 팀원이 준 원천 엑셀 폴더. 프로젝트 안(git 제외)을 먼저 보고, 없으면 예전 위치(~/찐파이널)를 본다
PROJECT_SOURCE_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "원천엑셀"
OLD_SOURCE_DIR = Path.home() / "찐파이널" / "raw" / "고배당 관련 데이터"
DEFAULT_SOURCE_DIR = PROJECT_SOURCE_DIR if PROJECT_SOURCE_DIR.exists() else OLD_SOURCE_DIR

FILES = {
    "01": "01_DART배당공시_원자료_638사.xlsx",
    "02": "02_고배당기업_연도별_배당재무_소급판정.xlsx",
    "04": "04_DART현금흐름표_배당금지급액_638사_2023_2025.xlsx",
    "04-1": "04-1_DART현금흐름표_배당계정_포함제외판정.xlsx",
    "04-2": "04-2_DART재무상태표_현금흐름표_원자료_638사_2023_2025.xlsx",
    "05": "05_배당결정공시_638사_2023_20261020.xlsx",
    "07": "07_KRX종목코드_보통주우선주_조회표_638사_20261019.xlsx",
    "09": "09_KIND고배당공시_원문대조_638사_20261020.xlsx",
}
SHEETS = {"07": "회사별 요약", "09": "대조"}  # 나머지는 첫 시트('데이터')

FS_DIV = {"연결": "CFS", "별도": "OFS"}
SJ_DIV = {"재무상태표": "BS", "현금흐름표": "CF"}


def read_source(key: str, source_dir: Path = DEFAULT_SOURCE_DIR) -> pd.DataFrame:
    """원천 파일을 모두 글자로 읽는다(코드 앞자리 0이 사라지지 않게)."""
    return pd.read_excel(Path(source_dir) / FILES[key], sheet_name=SHEETS.get(key, 0), dtype=str)


def text(v) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NA:
        return None
    s = str(v).strip()
    return s or None


def num(v) -> Decimal | None:
    s = text(v)
    if s is None or s in {"-", "−", "N/A", "nan"}:
        return None
    try:
        return Decimal(s.replace(",", "").replace(" ", ""))
    except InvalidOperation:
        return None


def integer(v) -> int | None:
    n = num(v)
    return int(n) if n is not None and n == n.to_integral_value() else None


def code8(v) -> str | None:
    s = text(v)
    return s.zfill(8) if s else None


def code6(v) -> str | None:
    s = text(v)
    return s.zfill(6) if s else None


def _rows(df: pd.DataFrame, mapping: dict, source: str) -> list[dict]:
    """mapping: {새 열 이름: (원천 열 이름, 변환 함수)}"""
    out = []
    for rec in df.to_dict("records"):
        row = {new: fn(rec.get(old)) for new, (old, fn) in mapping.items()}
        row["source_file"] = source
        out.append(row)
    return out


def kind_list(df09: pd.DataFrame) -> list[dict]:
    return _rows(df09, {
        "corp_name": ("회사명", text),
        "corp_code": ("DART고유번호", code8),
        "is_high_dividend": ("고배당기업여부", text),
        "final_rcept_no": ("최종_접수번호", text),
        "final_disclosed_on": ("최종_공시일", text),
        "decision_date": ("결정일자", text),
        "b2024_won": ("원문_2024배당소득(원)", num),
        "prev_year": ("원문_직전연도", text),
        "prev_payout_pct": ("원문_직전배당성향(%)", num),
        "prev_d_won": ("원문_직전이익배당금액(원)", num),
        "prevprev_d_won": ("원문_전전이익배당금액(원)", num),
        "growth_pct": ("원문_증가율(%)", num),
        "reduction_note": ("감액배당_문구", text),
        "link": ("DART링크", text),
    }, FILES["09"])


def dart_dividend_item(df01: pd.DataFrame) -> list[dict]:
    return _rows(df01, {
        "corp_code": ("DART고유번호", code8),
        "corp_name": ("회사명", text),
        "bsns_year": ("사업연도", integer),
        "item": ("항목_DART원문", text),
        "stock_kind": ("주식종류_DART원문", text),
        "value": ("값", text),
        "is_dash": ("DART에_대시표기", text),
        "col_02": ("02파일_열이름", text),
        "rcept_no": ("DART접수번호", text),
    }, FILES["01"])


def dart_financial(df42: pd.DataFrame) -> list[dict]:
    return _rows(df42, {
        "corp_code": ("DART고유번호", code8),
        "corp_name": ("회사명", text),
        "bsns_year": ("사업연도", integer),
        "fs_div": ("재무제표_기준", lambda v: FS_DIV.get(text(v), text(v))),
        "sj_div": ("재무제표_종류", lambda v: SJ_DIV.get(text(v), text(v))),
        "account_nm": ("계정명", text),
        "account_id": ("계정ID", text),
        "thstrm_amount": ("당기금액(원)", num),
        "frmtrm_amount": ("전기금액(원)", num),
        "term_name": ("기수", text),
        "ord": ("표시순서", integer),
        "currency": ("통화", text),
        "rcept_no": ("DART접수번호_재무", text),
    }, FILES["04-2"])


def cf_dividend_account(df41: pd.DataFrame) -> list[dict]:
    return _rows(df41, {
        "corp_code": ("DART고유번호", code8),
        "corp_name": ("회사명", text),
        "bsns_year": ("사업연도", integer),
        "fs_div": ("재무제표_기준", lambda v: FS_DIV.get(text(v), text(v))),
        "judgement": ("판정", text),
        "account_nm": ("계정명", text),
        "account_id": ("계정ID", text),
        "thstrm_amount": ("당기금액(원)", num),
        "frmtrm_amount": ("전기금액(원)", num),
        "term_name": ("기수", text),
        "ord": ("표시순서", integer),
        "currency": ("통화", text),
        "rcept_no": ("DART접수번호_재무", text),
    }, FILES["04-1"])


def cf_dividend_paid(df04: pd.DataFrame) -> list[dict]:
    return _rows(df04, {
        "corp_code": ("DART고유번호", code8),
        "corp_name": ("회사명", text),
        "fiscal_month": ("결산월", text),
        "bsns_year": ("사업연도", integer),
        "fs_div": ("재무제표_기준", lambda v: FS_DIV.get(text(v), text(v))),
        "rcept_no": ("DART접수번호_재무", text),
        "paid_mil": ("배당금지급액(백만원)", num),
        "prev_paid_mil": ("전기_배당금지급액(백만원)", num),
        "n_accounts": ("포함계정수", integer),
        "accounts": ("포함계정명", text),
        "nci_paid_mil": ("참고_비지배배당(백만원)", num),
        "check_accounts": ("확인필요_계정", text),
        "status": ("상태", text),
    }, FILES["04"])


def dividend_decision(df05: pd.DataFrame) -> list[dict]:
    return _rows(df05, {
        "rcept_no": ("접수번호", text),
        "corp_code": ("DART고유번호", code8),
        "corp_name": ("회사명", text),
        "fiscal_month": ("결산월", text),
        "disclosed_on": ("공시일", text),
        "report_nm": ("공시명", text),
        "is_correction": ("정정공시", lambda v: text(v) == "Y"),
        "div_kind": ("배당구분", text),
        "div_type": ("배당종류", text),
        "attributed_year": ("귀속사업연도(추정)", integer),
        "dps_common_won": ("주당배당금_보통주(원)", num),
        "dps_pref_won": ("주당배당금_종류주(원)", num),
        "differential": ("차등배당여부", text),
        "yield_common_pct": ("시가배당율_보통주(%)", num),
        "yield_pref_pct": ("시가배당율_종류주(%)", num),
        "total_won": ("배당금총액(원)", num),
        "total_mil": ("배당금총액(백만원)", num),
        "record_date": ("배당기준일", text),
        "pay_date": ("지급예정일", text),
        "agm": ("주총개최여부", text),
        "agm_date": ("주총예정일", text),
        "board_date": ("이사회결의일", text),
        "origin": ("원문출처", text),
        "parse_status": ("파싱상태", text),
        "link": ("DART링크", text),
    }, FILES["05"])


KRX_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "krx"


def _wide_to_rows(df: pd.DataFrame, key: str, value: str) -> list[tuple]:
    """날짜를 행 이름으로 둔 가로형 표 → (열 이름, 날짜, 값). 빈칸은 건너뛰고, 숫자가 아니거나 0 이하면 멈춘다."""
    long = df.rename_axis("trade_date").reset_index().melt(id_vars="trade_date", var_name=key, value_name=value)
    long = long[long[value].notna() & (long[value].astype(str).str.strip() != "")]
    dates = pd.to_datetime(long["trade_date"], format="%Y-%m-%d", errors="coerce")
    vals = pd.to_numeric(long[value], errors="coerce")
    bad = long[dates.isna() | vals.isna() | (vals <= 0)]
    if len(bad):
        raise ValueError(f"날짜나 가격을 읽을 수 없는 칸 {len(bad)}개, 예: {bad.head(3).to_dict('records')}")
    return list(zip(long[key], dates.dt.date, long[value].map(lambda v: Decimal(str(v).strip()))))


def krx_prices(df_wide: pd.DataFrame, source: str) -> list[dict]:
    """KRX prices.csv(행: 거래일, 열: corp_code, 값: 수정 종가) → raw.krx_price_daily."""
    return [{"corp_code": code8(c), "trade_date": d, "close_adj": v, "source_file": source}
            for c, d, v in _wide_to_rows(df_wide, "corp_code", "close_adj")]


def krx_market_index(df: pd.DataFrame, source: str) -> list[dict]:
    """KRX market.csv(행: 거래일, 열: 'KOSPI 종가' 등) → raw.krx_market_index."""
    df = df.rename(columns=lambda c: str(c).replace("종가", "").strip())
    return [{"market": m, "trade_date": d, "close": v, "source_file": source}
            for m, d, v in _wide_to_rows(df, "market", "close")]


def krx_day_status(df_status: pd.DataFrame, df_targets: pd.DataFrame, source: str) -> list[dict]:
    """KRX 일별상태.csv(종목코드, 거래일, 종가, 상태) → raw.krx_day_status.

    corp_code는 대상목록.csv의 종목코드로 찾는다. 노트북의 열 이름 매핑은 영문 포함 코드(0008Z0)를
    다른 회사로 바꾼 적이 있어 쓰지 않는다. 대상목록에 없는 종목코드가 있으면 멈춘다.
    """
    to_corp = dict(zip(df_targets["종목코드"].map(code6), df_targets["corp_code"].map(code8)))
    codes = df_status["종목코드"].map(code6)
    missing = sorted(set(codes) - set(to_corp))
    if missing:
        raise ValueError(f"대상목록에 없는 종목코드 {len(missing)}개, 예: {missing[:3]}")
    dates = pd.to_datetime(df_status["거래일"], format="%Y-%m-%d")
    return [{"corp_code": to_corp[c], "stock_code": c, "trade_date": d.date(), "close_last": num(v),
             "status": text(s), "source_file": source}
            for c, d, v, s in zip(codes, dates, df_status["종가"], df_status["상태"])]


def read_krx(path: Path) -> pd.DataFrame:
    """KRX 노트북이 만든 가로형 CSV(utf-8-sig, 첫 열이 날짜)를 글자로 읽는다."""
    return pd.read_csv(path, dtype=str, index_col=0, encoding="utf-8-sig")


def read_krx_table(path: Path) -> pd.DataFrame:
    """KRX 노트북이 만든 세로형 CSV(일별상태·대상목록)를 글자로 읽는다."""
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig")


RAW_BUILDERS = {
    "raw.kind_list": ("09", kind_list),
    "raw.dart_dividend_item": ("01", dart_dividend_item),
    "raw.dart_financial": ("04-2", dart_financial),
    "raw.cf_dividend_account": ("04-1", cf_dividend_account),
    "raw.cf_dividend_paid": ("04", cf_dividend_paid),
    "raw.dividend_decision": ("05", dividend_decision),
}
