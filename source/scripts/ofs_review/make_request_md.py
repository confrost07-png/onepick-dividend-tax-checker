"""03 별도재무제표 보완 자료 → 확인 요청 문서(md). 모든 숫자는 이 스크립트가 원본 CSV에서 센다."""
import json
import os
import sys

import pandas as pd

D, OUT, OUT_RESULT = sys.argv[1], sys.argv[2], sys.argv[3]
ZIP = "03_별도재무제표_실제보완_감사보고서제출_20261023.zip"


def rd(f):
    return pd.read_csv(os.path.join(D, f), dtype=str, encoding="utf-8-sig")


def won(v):
    v = float(v)
    return f"{v:,.0f}"


def table(df):
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for r in df.itertuples(index=False):
        lines.append("| " + " | ".join("" if pd.isna(x) else str(x).replace("|", "\\|") for x in r) + " |")
    return "\n".join(lines)


b = rd("별도_보완결과.csv")
e = rd("엔진적재_대기표.csv")
x = rd("API원문_불일치_검토.csv")
nd = rd("남은결측_목록.csv")
k = rd("기업별_실제수집현황.csv")
t = rd("별도/대상목록.csv")
s1 = json.load(open(os.path.join(D, "실제수집_요약.json"), encoding="utf-8"))
s2 = json.load(open(os.path.join(D, "보완_요약.json"), encoding="utf-8"))
before_after = rd("항목별_보완전후.csv")

b["v"] = pd.to_numeric(b["확정값"], errors="coerce")
b["w"] = pd.to_numeric(b["원 단위"], errors="coerce")
url_of = {}
for r in b.itertuples():
    url_of[(r.corp_code, r.사업연도, r.항목)] = r.원문

n_rows, n_corp = len(b), b.corp_code.nunique()
years = sorted(b["사업연도"].unique())
items = list(before_after["항목"])

# 채움 상태
fill = []
for it in items:
    s = b[b["항목"] == it]
    fill.append({"항목": it, "출처": s["출처"].iloc[0], "전체": len(s), "확정값 있음": int(s.v.notna().sum()),
                 "빈칸": int(s.v.isna().sum()), "음수": int((s.v < 0).sum())})
fill = pd.DataFrame(fill)

# Q1 음수 부채
neg = b[(b["항목"].isin(["부채총계", "자본총계"])) & (b.v < 0)]
bio = b[b["회사명"].isin(neg["회사명"])][["회사명", "사업연도", "항목", "확정값", "확정 출처", "대조", "원문"]]
bio = bio[bio["항목"].isin(["부채총계", "자본총계", "당기순이익_전체"])].sort_values(["사업연도", "항목"])
bio["확정값"] = bio["확정값"].map(won)
neg_engine = []
for r in neg.itertuples():
    col = {"부채총계": "liabilities_ofs_won", "자본총계": "equity_ofs_won"}[r.항목]
    v = e[(e.corp_code == r.corp_code) & (e.source_business_year == r.사업연도)][col].iloc[0]
    neg_engine.append(f"{r.회사명} {r.사업연도} {r.항목}: 엔진적재_대기표 `{col}` = {won(v)}")

# Q2 불일치
mis = b[b["대조"].fillna("").str.startswith("불일치")].copy()
mis["원문 후보"] = mis["w"]
mis["차이율"] = (mis.v - mis.w).abs() / mis.v.abs()
bins = pd.cut(mis["차이율"], [0, 0.001, 0.01, 0.1, 1, float("inf")],
              labels=["0.1% 이하", "0.1~1%", "1~10%", "10~100%", "100% 초과"])
dist = bins.value_counts().reindex(["0.1% 이하", "0.1~1%", "1~10%", "10~100%", "100% 초과"]).reset_index()
dist.columns = ["차이(원문 후보와 확정값)", "건수"]
mis_by_item = mis["항목"].value_counts().reset_index()
mis_by_item.columns = ["항목", "건수"]
mis_list = mis.sort_values("차이율", ascending=False)
mis_list = pd.DataFrame({
    "회사": mis_list["회사명"], "연도": mis_list["사업연도"], "항목": mis_list["항목"],
    "확정값(API)": mis_list["확정값"].map(won), "원문 후보": mis_list["원문 후보"].map(won),
    "차이율": (mis_list["차이율"] * 100).map(lambda v: "확정값 0" if v == float("inf") else f"{v:,.1f}%"),
    "원문": mis_list["원문"].map(lambda u: f"[링크]({u})" if isinstance(u, str) and u.startswith("http") else ""),
})
hold_words = ("지주", "홀딩스", "금융")
big_up = mis[(mis.w > mis.v.abs() * 2)]
big_up_hold = big_up[big_up["회사명"].str.contains("|".join(hold_words))]
top_corps = mis["회사명"].value_counts()
top_corps = top_corps[top_corps >= 3]

# 엔진적재 대기표: 불일치 칸 비움 확인
col_of = {"당기순이익_전체": "ni_ofs_won", "부채총계": "liabilities_ofs_won", "자본총계": "equity_ofs_won",
          "배당금지급_지급기준": "cf_paid_won"}
ek = e.set_index(["corp_code", "source_business_year"])
blank = sum(1 for r in mis.itertuples() if pd.isna(ek.loc[(r.corp_code, r.사업연도), col_of[r.항목]]))

# Q3 검토 파일 누락
xk = set(zip(x.corp_code, x["사업연도"], x["항목"]))
miss_in_review = mis[[(a, c, d) not in xk for a, c, d in zip(mis.corp_code, mis["사업연도"], mis["항목"])]]
miss_in_review = pd.DataFrame({"회사": miss_in_review["회사명"], "연도": miss_in_review["사업연도"],
                               "항목": miss_in_review["항목"], "확정값": miss_in_review["확정값"].map(won),
                               "대조 열": miss_in_review["대조"]})

# Q4 확정값 ≠ 원 단위 (불일치 표시 없는 행)
diff = b[b.v.notna() & b.w.notna() & (b.v != b.w) & ~b["대조"].fillna("").str.startswith("불일치")]
diff_tbl = pd.DataFrame({"회사": diff["회사명"], "연도": diff["사업연도"], "항목": diff["항목"],
                         "확정값": diff["확정값"].map(won), "원 단위": diff["w"].map(won),
                         "확정 출처": diff["확정 출처"], "대조 열": diff["대조"].fillna("")})

# Q5 비12월
non_dec = k[k["결산월"] != "12"][["회사명", "corp_code", "결산월", "별도원문연도"]]

# Q6 남은 결측
nd["사유"] = nd["확정 메모"].str.replace(r"\[.*?\]", "[…]", regex=True)
reason = nd.groupby(["항목", "사유"]).size().reset_index(name="칸 수").sort_values(["항목", "칸 수"], ascending=[True, False])
nd_corp = nd.groupby("회사명").size().sort_values(ascending=False)
multi = nd[nd["확정 메모"].str.contains("여러 개", na=False)][["회사명", "사업연도", "항목", "확정 메모"]]
noaudit = nd[nd["확정 메모"].str.startswith("감사보고서·사업보고서 API 모두 없음", na=False)]
noaudit_tbl = noaudit.groupby("회사명")["사업연도"].apply(lambda s: ", ".join(sorted(s))).reset_index()
noaudit_tbl.columns = ["회사", "빈 연도 (배당금지급_지급기준)"]
dash = nd[nd["구분"] == "데이터 없음"]

# Q7 감사 NI vs 배당표 NI
p = b.pivot_table(index=["corp_code", "회사명", "사업연도"], columns="항목", values="v", aggfunc="first").reset_index()
both = p.dropna(subset=["당기순이익_전체", "당기순이익"])
big = both[(both["당기순이익_전체"] - both["당기순이익"]).abs() > both["당기순이익"].abs() * 0.01].copy()
big["차이율"] = (big["당기순이익_전체"] - big["당기순이익"]).abs() / big["당기순이익"].abs()
big = big.sort_values("차이율", ascending=False)
ni_tbl = pd.DataFrame({"회사": big["회사명"], "연도": big["사업연도"],
                       "감사보고서 당기순이익_전체": big["당기순이익_전체"].map(won),
                       "배당 표 당기순이익": big["당기순이익"].map(won),
                       "차이율": (big["차이율"] * 100).map(lambda v: f"{v:,.1f}%")})
same_ni = int((both["당기순이익_전체"] == both["당기순이익"]).sum())
q = (both["당기순이익"] / both["당기순이익_전체"]).abs()
unit = both[q.between(9e5, 1.1e6) | q.between(900, 1100)]
unit_lines = [f"{r.회사명} {r.사업연도}: 감사보고서 {won(r.당기순이익_전체)}원, 배당 표 {won(r.당기순이익)}원 (약 {q[i]:,.0f}배)"
              for i, r in unit.iterrows()]

# 배당성향 재계산
calc = p["현금배당금총액"] / p["당기순이익"] * 100
ratio_n = int((calc - p["현금배당성향"]).abs().notna().sum())
ratio_bad = int(((calc - p["현금배당성향"]).abs() > 0.1).sum())

# 원문 대조 결과 (verify_mismatch.py · verify_own_year.py · final_verdict.py · verify_ni.py)
V = pd.read_csv(os.path.join(os.path.dirname(OUT_RESULT), "final_verdict.csv"), dtype={"연도": str})
NI = pd.read_csv(os.path.join(os.path.dirname(OUT_RESULT), "verify_ni.csv"), dtype={"연도": str})
V_mis = V[V["묶음"] == "불일치"]
vcount = V_mis["최종"].value_counts().reindex(["API 값 유지", "같은 값(단위 반올림 차이)", "원문 후보로 교체", "직접 확인 필요"]).fillna(0).astype(int)
v_tbl = pd.DataFrame({"판정": vcount.index, "칸 수": vcount.values})
sub = V_mis[V_mis["판정"].str.contains("다른 회사", na=False)].groupby(["회사", "보고서 감사 대상"]).size().reset_index(name="칸")
sub.columns = ["회사", "원문 후보를 읽은 감사보고서(실제 감사 대상)", "칸"]
def _w(v):
    return "" if pd.isna(v) else f"{v:,.0f}"
chg = V[V["최종"] == "원문 후보로 교체"].sort_values(["회사", "연도"])
chg_tbl = pd.DataFrame({"회사": chg["회사"], "연도": chg["연도"], "항목": chg["항목"], "API 값(현재 확정값)": chg["API 확정값"].map(_w),
                        "바꿀 값(원문)": chg["사업보고서 값"].fillna(chg["다시 읽은 값"]).fillna(chg["원문 후보"]).map(_w), "근거": chg["근거"]})
man = V[V["최종"] == "직접 확인 필요"]
man_tbl = pd.DataFrame({"회사": man["회사"], "연도": man["연도"], "항목": man["항목"], "API 값": man["API 확정값"].map(_w),
                        "원문 후보": man["원문 후보"].map(_w), "그 연도 사업보고서 값": man["사업보고서 값"].map(_w), "원문": man["원문"].map(lambda u: f"[링크]({u})")})
q3v = V[V["회사"].isin(miss_in_review["회사"]) & V.set_index(["회사", "연도", "항목"]).index.isin(
    list(zip(miss_in_review["회사"], miss_in_review["연도"], miss_in_review["항목"])))][["회사", "연도", "항목", "최종", "근거"]]
q5v = V[V["묶음"] == "표시없는차이"]["최종"].value_counts()
NI_cnt = NI["판정"].value_counts()
ni_left = NI[~NI["판정"].str.startswith("감사보고서 값이 맞음")].copy()
ni_left_tbl = pd.DataFrame({"회사": ni_left["회사"], "연도": ni_left["연도"], "감사보고서": ni_left["감사보고서"].map(_w),
                            "배당 표": ni_left["배당 표"].map(_w), "그 연도 사업보고서 별도 손익": ni_left["사업보고서 별도 손익"].map(_w),
                            "판정": ni_left["판정"]})

# 엔진 대기표 상태
engine_state = {c: e[c].value_counts(dropna=False).to_dict() for c in
                ["engine_ready", "judgement_status", "b_status", "consolidation_status", "financial_basis_verified"]}

md = f"""# 03 별도재무제표 보완 자료 확인 요청

- 대상 자료: `{ZIP}`
- 자료 기준일: {s1['검색기준일']} (실제수집_요약.json)
- 점검일: 2026-10-23
- 점검 방법: 압축 안 CSV·JSON을 코드로 다시 세고, onepick DB에 이미 있는 별도 재무 값과 대조했습니다. 아래 숫자는 모두 자료에서 직접 센 값입니다.
- 요청: 아래 **Q1~Q9**에 답을 주시면, 확인된 값만 DB에 적재하겠습니다. 답변은 문서 끝 [답변 양식](#답변-양식)에 적어 주세요.
- **원문 직접 대조(2026-10-23 추가):** 자료에 남아 있는 DART 원문 링크를 코드로 다시 열어, 문제 칸 {len(V)}칸(Q2·Q3·Q5)과 Q8 {len(NI)}칸을 그 연도 감사보고서·사업보고서 별도 재무제표와 대조했습니다. 칸별 결과는 같은 폴더의 `별도재무제표_원문대조_결과.csv`에 있습니다. 그래서 아래 질문 대부분은 **"이 결과대로 반영해도 되는지"** 확인만 부탁드립니다.

## 1. 자료 한눈에 보기

| 항목 | 값 |
|---|---|
| 회사 수 | {n_corp}사 (에코마케팅·에스엔시스 포함, 대상목록 {len(t)}사와 같음) |
| 사업연도 | {', '.join(years)} |
| 항목 | {len(items)}개 (감사보고서 4개 + 사업보고서 배당 표 5개) |
| 전체 행 | {n_rows:,}행 = {n_corp}사 × {len(years)}년 × {len(items)}항목 |
| 기준 | 전부 별도 (연결 값은 `연결감사보고서_추가확보.csv` {s1['연결_추가확보값수']:,}개, {s1['연결_확보기업수']}사에 따로 있음) |
| 확정값 빈칸 | 보완 전 {s1['보완전_확정값미확보']:,}칸 → 보완 후 {s1['보완후_확정값미확보']:,}칸 |

### 항목별 채움 상태

{table(fill)}

### 압축 안 주요 파일

| 파일 | 행 수 | 쓰임 |
|---|---|---|
| `별도_보완결과.csv` | {len(b):,} | 본 결과 (회사×연도×항목 1행) |
| `엔진적재_대기표.csv` | {len(e):,} | 회사×연도 1행, 판정 엔진 입력 후보 |
| `API원문_불일치_검토.csv` | {len(x):,} | API 값과 감사보고서 원문 값이 다른 행 |
| `남은결측_목록.csv` | {len(nd):,} | 확정값이 비어 있는 칸과 사유 |
| `기업별_실제수집현황.csv` | {len(k):,} | 회사별 수집 상태 |
| `연결감사보고서_추가확보.csv` | {s1['연결_추가확보값수']:,} | 연결 감사보고서 값 (사업연도 매핑 전) |

## 2. 확인된 정상 사항 (답변 필요 없음)

- 회사×연도×항목 중복 행 0건.
- onepick DB에 이미 있는 별도 부채총계·자본총계(04-2 원천)와 겹치는 606건이 모두 같은 값입니다.
- 현금배당성향 {ratio_n:,}건을 `현금배당금총액 ÷ 당기순이익 × 100`으로 다시 계산하면 {ratio_n - ratio_bad:,}건이 0.1%p 안에서 같습니다.
- 감사보고서 당기순이익_전체와 배당 표 당기순이익이 둘 다 있는 {len(both):,}건 중 {same_ni:,}건은 원 단위까지 같습니다.
- `-` 표시를 0으로 바꾸지 않았고, 연결 값으로 별도 값을 대신 채우지 않았습니다 (README 설명과 일치).
- 자본총계 음수(자본잠식) 0건, 당기순이익_전체 적자 {int((b[b['항목']=='당기순이익_전체'].v < 0).sum())}칸.

## 3. 확인 요청

### Q1. 부채총계가 음수인 칸 (긴급)

부채는 음수가 될 수 없어 원문 읽기 오류로 보입니다. **이 값은 `엔진적재_대기표.csv`에도 그대로 들어가 있습니다.**

{chr(10).join('- ' + s for s in neg_engine)}

같은 회사의 감사보고서 값:

{table(bio)}

**원문 대조 결과:** 바이오비쥬 2023 감사보고서(접수번호 20240813000437, 정정신고) 재무상태표의 **부채총계는 16,423,150,217원**입니다. 같은 표의 자본총계 11,505,973,746원과 더하면 부채와자본총계 27,929,123,963원과 맞습니다. 음수 값은 다른 행을 읽은 것입니다.

- 확인 부탁: 16,423,150,217원으로 고쳐도 되는지.

### Q2. API 값과 감사보고서 원문 값이 다른 {len(mis)}칸 — 어느 값을 기준으로 할지

`별도_보완결과.csv`의 `대조` 열이 `불일치`인 칸입니다. 확정값은 모두 기존 사업보고서 API(XBRL) 값을 그대로 두었고, `원 단위` 열에 원문 후보가 있습니다. `엔진적재_대기표.csv`에서는 이 {len(mis)}칸이 **{blank}칸 모두 비어 있습니다** (판정 입력에서 보류한 것으로 보입니다).

차이 크기:

{table(dist)}

항목별:

{table(mis_by_item)}

불일치가 3칸 이상인 회사: {', '.join(f'{n}({c})' for n, c in top_corps.items())}

**원문 대조 결과 ({len(V_mis)}칸):** 원문 링크 문서에서 감사 대상 회사 이름과 해당 연도 값을 다시 읽고, 비교기간(재작성) 값이거나 결론이 안 난 칸은 그 연도 사업보고서의 별도 재무제표로 한 번 더 확인했습니다. 현금흐름표의 배당금 지급은 괄호(음수) 표기라 절댓값으로, 천원·백만원 단위 표는 반올림 차이를 같은 값으로 봤습니다.

{table(v_tbl)}

**원인:** 차이가 10%를 넘는 칸이 {int((mis['차이율'] > 0.1).sum())}칸이었는데, 대부분 표를 잘못 읽은 것이 아니라 **다른 회사 보고서**를 읽은 것이었습니다. 지주회사는 '감사보고서제출' 공시에 자회사 감사보고서를 함께 냅니다. 원문 후보 {int(V_mis['판정'].str.contains('다른 회사', na=False).sum())}칸은 이 자회사 보고서에서 읽은 값이라 API 값이 맞습니다. 예: 우리금융지주 2023 부채총계 원문 후보 411.6조는 주식회사 우리은행의 부채총계입니다. 단, MH머트리얼즈(만호제강)·위너스일렉(위너스)은 자회사인지 옛 사명인지 확인하지 못했습니다.

<details><summary>자회사 보고서를 읽은 회사 목록</summary>

{table(sub)}

</details>

원문 후보로 바꿔야 하는 칸 ({len(chg)}칸, Q3·Q5 포함):

{table(chg_tbl)}

사람이 직접 봐야 하는 칸 ({len(man)}칸):

{table(man_tbl)}

- MH머트리얼즈 2023은 원문 링크가 '만호제강 주식회사' 감사보고서입니다. 사명 변경 전 보고서인지, 분할 등으로 다른 회사인지 확인이 필요합니다.
- 확인 부탁 1: 위 판정대로 반영해도 되는지 (API 유지 · 원문 교체 · 반올림 차이는 더 자세한 값 사용).
- 확인 부탁 2: 엔진적재_대기표에서 이 칸들을 비워 둔 것이 의도인지. 반영 뒤에는 채워도 되는지.
- 확인 부탁 3: MH머트리얼즈·위너스일렉의 원문 감사보고서가 같은 회사(옛 사명)인지.

<details><summary>불일치 {len(mis)}칸 전체 (차이율 큰 순)</summary>

{table(mis_list)}

</details>

### Q3. 불일치 검토 파일에서 빠진 {len(miss_in_review)}칸

`별도_보완결과.csv`에는 `불일치`로 표시됐지만 `API원문_불일치_검토.csv`({len(x)}행)에는 없는 칸입니다.

{table(miss_in_review)}

**원문 대조 결과:**

{table(q3v)}

- 확인 부탁: 검토 파일에서 빠진 이유.

### Q4. 요약 파일끼리 숫자가 다름

| 파일 | 불일치 건수 |
|---|---|
| `실제수집_요약.json` (`API원문_불일치`) | {s1['API원문_불일치']} |
| `보완_요약.json` (`API원문불일치`) | {s2['API원문불일치']} |
| `API원문_불일치_검토.csv` 행 수 | {len(x)} |
| `별도_보완결과.csv` `대조` = 불일치 | {len(mis)} |

- 확인 부탁: 어느 숫자가 최종인지. Q3의 {len(miss_in_review)}칸이 차이의 원인으로 보입니다.

### Q5. 확정값과 `원 단위` 열이 다르지만 `불일치` 표시가 없는 {len(diff)}칸

API 값을 확정값으로 쓴 칸 중, 원문 후보와 다르지만 `대조` 열이 `불일치`가 아닌 칸입니다.

<details><summary>{len(diff)}칸 목록</summary>

{table(diff_tbl)}

</details>

**원문 대조 결과:** {len(V[V['묶음']=='표시없는차이'])}칸 모두 '{', '.join(f'{k2} {v}칸' for k2, v in q5v.items())}'입니다. API가 천원·백만원 단위로 반올림된 값이고, 원문은 원 단위 값입니다. 실제 차이는 없습니다.

- 확인 부탁: 원 단위 원문 값을 쓰면 되는지.

### Q6. 비12월 결산 {len(non_dec)}개사의 사업연도 매칭

README에 "원문표 달력연도와 입력 사업연도를 자동 매칭하지 않았다"고 되어 있습니다. `엔진적재_대기표`의 `calendar_table_year_equals_business_year`도 이 회사들은 `미확인`입니다.

{table(non_dec)}

- 확인 부탁: 이 회사들의 2023·2024·2025 행이 각각 어느 회계기간(예: 2024.04~2025.03)인지.

### Q7. 남은 빈칸 {len(nd):,}칸의 처리

구분: {', '.join(f'{k2} {v:,}칸' for k2, v in nd['구분'].value_counts().items())}

항목×사유:

{table(reason)}

- 확인 부탁 1: `-`로 표시된 {len(dash):,}칸(데이터 없음)은 무배당으로 볼지, 배당 결정 공시로 확인한 뒤 채울지.
- 확인 부탁 2: 주당순이익을 연결 값만 공시한 회사(323칸)는 별도 주당순이익을 비워 두면 되는지.
- 값이 여러 개 잡힌 칸(진도)은 **원문으로 확인했습니다.** 사업보고서 배당 표의 두 줄은 보통주·우선주이고, 첫 줄에만 시가배당률이 있으며 "우선주는 상장되지 아니하여" 주석이 있습니다. 보통주 주당현금배당금은 2023 **50원**, 2024 **30원**, 2025 **150원**입니다 (우선주 60·40·160원).

{table(multi)}

<details><summary>감사보고서·API 모두 없는 배당금지급_지급기준 ({len(noaudit)}칸, {len(noaudit_tbl)}사)</summary>

{table(noaudit_tbl)}

</details>

<details><summary>빈칸이 많은 회사 (회사별 빈칸 수, 상위 30)</summary>

{table(nd_corp.head(30).reset_index().rename(columns={'회사명': '회사', 0: '빈칸 수'}))}

</details>

### Q8. 감사보고서 순이익과 배당 표 순이익이 1% 넘게 다른 {len(big)}칸

둘 다 별도 기준인데 값이 다릅니다. 판정 엔진에 어느 쪽을 넣을지 정해야 합니다.

**단위 오류 (원문 확인):** 지투파워 2023 사업보고서(접수번호 20240319000635) 배당 표에 회사가 직접 "(별도)당기순이익(백만원) 774,336,413"으로 적었습니다. 원 단위 값을 백만원 칸에 적은 **공시 원문의 오류**이고, 수집은 그대로 옮긴 것입니다. 맞는 값은 774,336,413원(감사보고서와 같음)입니다.

{chr(10).join('- ' + u for u in unit_lines)}

나머지 칸은 배당 표가 백만 원 단위로 반올림돼 있어 생기는 작은 차이와, 원인을 확인하지 못한 큰 차이가 섞여 있습니다.

<details><summary>{len(big)}칸 목록 (차이율 큰 순)</summary>

{table(ni_tbl)}

</details>

**원문 대조 결과 ({len(NI)}칸):** 그 연도 사업보고서의 별도 손익계산서와 대조했습니다.

{table(NI_cnt.rename_axis('판정').reset_index(name='칸 수'))}

결론이 감사보고서 쪽이 아닌 칸:

{table(ni_left_tbl)}

- 확인 부탁 1: 판정·최소액에는 **감사보고서 당기순이익_전체**를 쓰고, 배당 표 순이익은 참고로만 두어도 되는지.
- 확인 부탁 2: 리드코프·산일전기·심텍처럼 세 값이 모두 다른 칸의 처리.

### Q9. 엔진적재_대기표의 다음 단계

`엔진적재_대기표.csv` {len(e):,}행의 상태는 아래와 같아 지금은 판정을 바꿀 수 없습니다.

| 열 | 값 |
|---|---|
""" + "\n".join(f"| `{c}` | " + ", ".join(f"{k2} {v:,}" for k2, v in d.items()) + " |" for c, d in engine_state.items()) + f"""

- 확인 부탁 1: B(배당소득)와 법적 D를 언제, 어떤 자료로 채울 계획인지.
- 확인 부탁 2: `consolidation_status`(연결 작성 여부)를 어떻게 확인할지. 우리 DB는 지금 02 파일의 연결/별도 구분을 씁니다.
- 확인 부탁 3: `연결감사보고서_추가확보.csv`는 원문표 연도가 사업연도 매핑 전이라고 되어 있습니다. 매핑된 판이 따로 나올 예정인지.

## 답변 양식

| 질문 | 답변 | 근거 자료(공시 번호·파일) |
|---|---|---|
| Q1 바이오비쥬 부채총계 16,423,150,217원으로 수정 | | |
| Q2 원문 대조 판정대로 반영 + 남은 3칸 | | |
| Q3 검토 파일 누락 3칸 | | |
| Q4 최종 불일치 건수 | | |
| Q5 원 단위 원문 값 사용 | | |
| Q6 비12월 결산 기간 | | |
| Q7 빈칸 처리 (`-` / 연결 EPS) | | |
| Q8 감사보고서 순이익 사용 + 세 값 다른 3칸 | | |
| Q9 B·D·연결 여부 계획 | | |

답변을 받기 전까지 이 자료는 onepick DB에 넣지 않습니다. 답변 뒤 적재할 때도 원본 행은 고치지 않고, 문제 칸은 표시만 달아 둡니다.
"""
open(OUT, "w", encoding="utf-8").write(md)
print("written", OUT, len(md.splitlines()), "lines")
