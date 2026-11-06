"""KIND 고배당기업 목록(엑셀 내려받기) 읽기와 결측 점검.

KIND는 공개 API가 없어 내려받은 파일을 읽는다. 화면에는 보이는데 읽으면 비는 흔한 원인과 대응:
- '.xls' 파일이 실제로는 HTML 표 → 첫 글자가 '<'이면 HTML 표로 읽음
- 종목코드가 숫자로 읽혀 앞자리 0이 빠짐(005930 → 5930) → 글자로 읽고 6자리로 맞춤
- 열 이름이 내려받을 때마다 조금씩 다름 → COLUMNS 별칭으로 맞춤
- 사업연도가 결산월과 맞지 않음(예: 12월 결산인데 사업연도 2026) → '점검' 목록에 올림. 값은 고치지 않음
- 종목코드로 DART 고유번호를 못 찾음 → 회사명으로 한 번 더 찾고, 그래도 없으면 '확인 불가'
- 종목코드 열이 없고 회사명이 KRX 약칭(줄임말)임 → build_company_map이 DART 정식 이름·종목명과 시장구분으로 찾음

실서비스에서는 공시 정보 이용 조건을 확인한다(PRD 6.1).
"""
from pathlib import Path

import pandas as pd

import re
from typing import Callable

from core.sources.base import OK, UNVERIFIED, squash, to_number
from core.sources.opendart import Dart, match_stock_codes, table_rows

# 표준 열 이름 → 파일에 나올 수 있는 이름(공백·괄호 무시하고 비교)
COLUMNS = {
    "회사명": ("회사명", "종목명", "기업명", "법인명"),
    "종목코드": ("종목코드", "단축코드", "코드"),
    "사업연도": ("사업연도", "결산연도", "대상사업연도"),
    "결산월": ("결산월", "결산기", "결산월(월)"),
    "배당성향": ("배당성향", "배당성향(%)", "현금배당성향", "현금배당성향(%)"),
    "시장구분": ("시장구분", "시장", "소속부"),
    "이익배당금증가율": ("이익배당금증가율", "이익배당금증가율(%)"),
    "공시제목": ("공시제목", "보고서명"),
}
REQUIRED = ("회사명",)


def _read_any(path: Path) -> pd.DataFrame:
    raw = path.read_bytes()
    if raw.lstrip()[:1] == b"<":  # KIND의 '엑셀' 내려받기는 HTML 표인 경우가 많다
        for enc in ("utf-8", "cp949", "euc-kr"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        rows = table_rows(text)
        if not rows:
            raise ValueError(f"표를 찾지 못함: {path}")
        width = len(rows[0])
        return pd.DataFrame([r + [""] * (width - len(r)) for r in rows[1:]], columns=rows[0], dtype=str)
    if path.suffix.lower() == ".csv":
        for enc in ("utf-8-sig", "cp949"):
            try:
                return pd.read_csv(path, dtype=str, encoding=enc)
            except UnicodeDecodeError:
                continue
    return pd.read_excel(path, dtype=str)


def _rename(df: pd.DataFrame) -> pd.DataFrame:
    lookup = {squash(alias): std for std, aliases in COLUMNS.items() for alias in aliases}
    renamed = {}
    for col in df.columns:
        key = squash(col)
        std = lookup.get(key) or lookup.get(key.split("(")[0])
        if std and std not in renamed.values():
            renamed[col] = std
    return df.rename(columns=renamed)


def load_kind_list(path, expected_year: int | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """KIND 목록을 읽어 (표, 점검 목록)을 돌려준다. 값은 고치지 않고 이상한 점만 점검 목록에 적는다."""
    path = Path(path)
    df = _rename(_read_any(path))
    missing = [c for c in REQUIRED if c not in df]
    if missing:
        raise ValueError(f"필수 열 {missing} 없음. 파일의 열: {list(df.columns)}")
    df = df.copy()
    if "종목코드" in df:
        df["종목코드"] = df["종목코드"].map(lambda c: "".join(ch for ch in str(c) if ch.isdigit()).zfill(6)
                                        if str(c).strip() not in ("", "nan", "None") else None)
    if "배당성향" in df:
        df["배당성향 숫자"] = df["배당성향"].map(to_number)

    issues = []
    for i, row in df.iterrows():
        name = row.get("회사명")
        if "종목코드" in df and pd.isna(row["종목코드"]):
            issues.append({"행": i, "회사명": name, "점검": "종목코드 비어 있음"})
        if "배당성향" in df and pd.isna(row.get("배당성향 숫자")):
            issues.append({"행": i, "회사명": name, "점검": f"배당성향 값 없음({row.get('배당성향')!r})"})
        if expected_year and "사업연도" in df:
            year = to_number(row.get("사업연도"))
            month = to_number(row.get("결산월")) if "결산월" in df else None
            if year is not None and year != expected_year:
                memo = f"사업연도 {year}(기대 {expected_year})"
                if month == 12:
                    memo += " · 12월 결산인데 연도가 다름: KIND 원문 확인"
                issues.append({"행": i, "회사명": name, "점검": memo})
    key = "종목코드" if "종목코드" in df else "회사명"
    dup = df[df[key].notna() & df.duplicated(key, keep=False)]
    for i, row in dup.iterrows():
        issues.append({"행": i, "회사명": row.get("회사명"), "점검": f"{key} {row[key]} 중복"})
    return df, pd.DataFrame(issues, columns=["행", "회사명", "점검"])


def attach_corp_codes(kind_df: pd.DataFrame, corp_df: pd.DataFrame) -> pd.DataFrame:
    """KIND 목록에 DART 고유번호를 붙인다. 종목코드 → 회사명 순서로 찾고 '매핑 상태'·'매핑 메모'를 남긴다."""
    by_code = match_stock_codes(corp_df, [c or "" for c in kind_df["종목코드"]])
    names = corp_df.assign(_key=corp_df["corp_name"].map(squash))
    out = kind_df.reset_index(drop=True).copy()
    out["corp_code"], out["매핑 상태"], out["매핑 메모"] = by_code["corp_code"], by_code["상태"], by_code["메모"]
    for i in out.index[out["매핑 상태"] != OK]:
        hit = names[names["_key"] == squash(out.at[i, "회사명"])]
        if len(hit) == 1:
            out.at[i, "corp_code"] = hit["corp_code"].iloc[0]
            out.at[i, "매핑 상태"] = OK
            out.at[i, "매핑 메모"] = "종목코드로 못 찾아 회사명으로 찾음: 확인 필요"
        else:
            out.at[i, "매핑 상태"] = UNVERIFIED
            out.at[i, "매핑 메모"] = f"{out.at[i, '매핑 메모']} · 회사명 후보 {len(hit)}개"
    return out


# --- KIND · OpenDART · 시장구분 매핑표 ---

MARKETS = {"유가": "유가", "유가증권": "유가", "코스피": "유가", "KOSPI": "유가", "코스닥": "코스닥", "KOSDAQ": "코스닥"}
FINANCE_KSIC = ("64", "65", "66")  # 한국표준산업분류 금융 및 보험업
MAP_COLUMNS = ["번호", "회사명", "시장구분", "사업연도", "결산월", "배당성향", "이익배당금증가율", "공시제목",
               "corp_code", "종목코드", "DART 회사명", "DART 종목명", "DART 시장", "DART 결산월", "업종코드", "금융업",
               "매핑 방법", "매핑 상태", "점검"]


def name_key(name) -> str:
    """회사명 비교용: 공백·가운뎃점·'(주)'·'주식회사'를 지우고 영문은 대문자로."""
    s = squash(name).upper()
    return re.sub(r"\(주\)|㈜|주식회사|\(유\)", "", s)


def build_company_map(kind_df: pd.DataFrame, corp_df: pd.DataFrame, dart: Dart, expected_year: int | None = None,
                      progress: Callable[[str], None] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """KIND 목록 한 행 = 한 회사에 DART 고유번호·종목코드·시장·결산월·업종을 붙인다. (매핑표, 점검표)를 돌려준다.

    찾는 순서(종목코드 열이 있으면 종목코드가 먼저):
    1) DART 정식 회사명과 같음 → 2) 정식 회사명이 KIND 이름으로 시작(줄임말)
    → 3) 같은 시장 상장사의 DART 종목명(약칭)과 같음(상장사 기업개황을 받아 비교, 남은 회사가 있을 때만)
    어느 단계든 기업개황의 시장구분이 KIND 시장구분과 맞아야 하고, 후보가 하나로 정해지지 않으면 '확인 불가'.
    값은 고치지 않고 다른 점은 '점검' 칸에 적는다.
    """
    say = progress or (lambda msg: None)
    listed = corp_df[corp_df["stock_code"].astype(str).str.strip() != ""].copy()
    listed["stock_code"] = listed["stock_code"].astype(str).str.strip().str.zfill(6)
    listed["_key"] = listed["corp_name"].map(name_key)
    profiles: dict[str, dict | None] = {}

    def profile(corp_code: str) -> dict | None:
        if corp_code not in profiles:
            got = dart.company(corp_code)
            profiles[corp_code] = got.value if got.found else None
        return profiles[corp_code]

    def confirm(cands: pd.DataFrame, key: str, market: str) -> tuple[pd.Series | None, str]:
        if cands.empty:
            return None, "후보 없음"
        cands = cands.head(30)
        good = [r for _, r in cands.iterrows() if (p := profile(r["corp_code"])) and (not market or p["시장"] == market)]
        if len(good) > 1:
            same_short = [r for r in good if name_key(profiles[r["corp_code"]]["stock_name"]) == key]
            good = same_short or good
        if len(good) == 1:
            return good[0], ""
        if not good:
            seen = ", ".join(f"{r['corp_name']}({(profiles.get(r['corp_code']) or {}).get('시장', '?')})" for _, r in cands.iterrows())
            return None, f"시장구분이 맞는 후보 없음: {seen}"
        return None, "후보 여러 개: " + ", ".join(r["corp_name"] for r in good)

    results, pending = {}, []
    for i, row in kind_df.reset_index(drop=True).iterrows():
        key, market = name_key(row["회사명"]), MARKETS.get(squash(row.get("시장구분", "")), "")
        code = row.get("종목코드") if "종목코드" in kind_df else None
        tries = []
        if code and not pd.isna(code):
            tries.append(("종목코드 일치", listed[listed["stock_code"] == code]))
        tries += [("회사명 일치", listed[listed["_key"] == key]),
                  ("회사명 앞부분 일치(줄임말)", listed[listed["_key"].str.startswith(key)] if len(key) >= 2 else listed.iloc[0:0])]
        memo = ""
        for how, cands in tries:
            pick, memo = confirm(cands, key, market)
            if pick is not None:
                results[i] = (pick, how, "")
                break
        else:
            pending.append((i, key, market, memo))
        if i % 100 == 0:
            say(f"{i}/{len(kind_df)} 처리 · 기업개황 {len(profiles)}건")

    if pending:
        markets = {m for _, _, m, _ in pending}
        used = {r[0]["corp_code"] for r in results.values()}
        pool = listed[~listed["corp_code"].isin(used)]
        say(f"남은 {len(pending)}곳: 상장사 {len(pool)}곳의 종목명을 받아 비교합니다(하루 한도 주의)")
        for n, (_, r) in enumerate(pool.iterrows()):
            profile(r["corp_code"])
            if n % 200 == 0:
                say(f"종목명 {n}/{len(pool)}")
        for i, key, market, memo in pending:
            cands = pool[pool["corp_code"].map(lambda c: bool(profiles.get(c)) and name_key(profiles[c]["stock_name"]) == key
                                               and (not market or profiles[c]["시장"] == market))]
            if len(cands) == 1:
                results[i] = (cands.iloc[0], "DART 종목명(약칭) 일치", "")
            else:
                results[i] = (None, "", memo if cands.empty else f"종목명 후보 {len(cands)}개")
        say(f"끝 · 시장 {sorted(markets)}")

    rows = []
    for i, row in kind_df.reset_index(drop=True).iterrows():
        pick, how, memo = results.get(i, (None, "", "후보 없음"))
        p = profiles.get(pick["corp_code"]) if pick is not None else None
        p = p or {}
        checks = []
        year = to_number(row.get("사업연도"))
        if expected_year and year is not None and year != expected_year:
            checks.append(f"사업연도 {year}(기대 {expected_year})")
        kind_month = str(row.get("결산월", "") or "").zfill(2)
        dart_month = str(p.get("acc_mt", "") or "").zfill(2)
        if kind_month != "12":
            checks.append(f"{kind_month}월 결산: 감사보고서·사업보고서 연도 확인")
        if p and dart_month != "00" and kind_month != dart_month:
            checks.append(f"결산월 다름(KIND {kind_month}, DART {dart_month})")
        finance = str(p.get("induty_code", ""))[:2] in FINANCE_KSIC if p else None
        if finance:
            checks.append("금융업: 재무제표 양식이 다름")
        if how and how not in ("회사명 일치", "종목코드 일치"):
            checks.append("매핑 확인 권장")
        rows.append({
            "번호": row.get("번호"), "회사명": row["회사명"], "시장구분": row.get("시장구분"),
            "사업연도": row.get("사업연도"), "결산월": row.get("결산월"), "배당성향": row.get("배당성향"),
            "이익배당금증가율": row.get("이익배당금증가율"), "공시제목": row.get("공시제목"),
            "corp_code": pick["corp_code"] if pick is not None else None,
            "종목코드": pick["stock_code"] if pick is not None else None,
            "DART 회사명": pick["corp_name"] if pick is not None else None,
            "DART 종목명": p.get("stock_name"), "DART 시장": p.get("시장"), "DART 결산월": p.get("acc_mt"),
            "업종코드": p.get("induty_code"), "금융업": finance,
            "매핑 방법": how, "매핑 상태": OK if pick is not None else UNVERIFIED,
            "점검": " · ".join(checks) if pick is not None else memo,
        })
    out = pd.DataFrame(rows, columns=MAP_COLUMNS)
    dup = out["corp_code"].notna() & out.duplicated("corp_code", keep=False)
    out.loc[dup, "매핑 상태"] = UNVERIFIED
    out.loc[dup, "점검"] = out.loc[dup, "점검"].fillna("") + " · 다른 행과 같은 고유번호"
    check = out[(out["매핑 상태"] != OK) | (out["점검"].fillna("") != "")]
    return out, check.reset_index(drop=True)
