"""PRD v0.1 → v0.2 수정사항(2026-10-22)을 document.xml에 반영한다."""
import re
import sys
from xml.sax.saxutils import escape

path = sys.argv[1]
x = open(path, encoding="utf-8").read()


def sub_text(old, new, count=1):
    """<w:t> 안의 글자만 바꾼다. 정확히 count번 나와야 한다."""
    global x
    pat = re.compile(r"(<w:t(?: [^>]*)?>)([^<]*)(</w:t>)")
    hits = 0

    def rep(m):
        nonlocal hits
        if old in m.group(2):
            hits += m.group(2).count(old)
            return m.group(1) + m.group(2).replace(old, escape(new)) + m.group(3)
        return m.group(0)

    x = pat.sub(rep, x)
    assert hits == count, f"{old!r}: {hits}번 (기대 {count})"


# 1-1. 회사 수 638 → 639
for old in ["638사의 배당·재무", "KIND 고배당기업 목록(638사)", "638사 수집, KIND", "2017~2025 · 638사",
            "2018~2025 · 638사", "2018~2026 · 638사", "매핑(638사)", "638사 배당·재무 1차 수집",
            "수집 현황표(638사)", "638사 판정·최소액 테이블"]:
    sub_text(old, old.replace("638", "639"))

# 2-1. 6.1 확보 상태·재무 단위
sub_text("2018~2025 · 639사 · 회사×연도(원)",
         "2018~2025 · 639사 · 지배주주 순이익·부채·자본은 백만 원(02), 재무상태표·현금흐름표 원자료는 원(04-2, 2023~2025)")
sub_text("API·원문 · 예정", "API·원문 · 보유")
sub_text("2023~2026 · 638사 · 배당 건",
         "639사 · 배당 결정 공시 2,754건(공시일 2023~2026-10-20, 귀속 2022~2026) · 현금흐름표 지급액 2023~2025(비12월 결산 7곳은 2026까지)")

# 1-2, 1-3. 6.2 원천 테이블
sub_text("배당 원천 (dart_dividend)", "배당 원천 (dart_dividend_item)")
sub_text("회사 × 사업연도 1행", "회사 × 사업연도 × 항목 × 주식종류 값 1개 (세로형 원자료)")
sub_text("PK (corp_code, bsns_year) / FK corp_code, rcept_no",
         "PK 없음(원자료 그대로 보관, 같은 키로 겹치는 행 4,326줄) / FK corp_code, rcept_no")
sub_text("회사 × 사업연도 × 계정 1행", "회사 × 사업연도 × 재무제표 종류 × 표시순서 1행")
sub_text("PK (corp_code, bsns_year, fs_div, account_id)", "PK (corp_code, bsns_year, fs_div, sj_div, ord)")
sub_text("회사 × 사업연도(배당 세 갈래, B·D)",
         "회사 × 사업연도(배당 세 갈래, B·D) · 세로형 원천을 가공(02)해 1행으로 만듦. 2026 귀속 기결의 배당은 05만 출처로 행 추가")

# 2-2. 원천 테이블 3개 추가 (배당 결정 공시 행을 복제)
i = x.find("배당 결정 공시 (dividend_decision)")
start = x.rfind("<w:tr>", 0, i)
end = x.find("</w:tr>", i) + len("</w:tr>")
row = re.sub(r' w14:(paraId|textId)="[^"]*"', "", x[start:end])
cells_old = ["배당 결정 공시 (dividend_decision)", "배당 결의 1건", "PK rcept_no / FK corp_code"]
new_rows = [
    ("KIND 고배당기업 목록 (kind_list)", "KIND 고배당기업 목록 1곳",
     "PK corp_name → core_company에서 corp_code로 매핑(639곳 1:1 확인)"),
    ("현금흐름표 배당금 지급액 (cf_dividend_paid)", "회사 × 사업연도 현금흐름표 배당금 지급액 1행",
     "PK (corp_code, bsns_year)"),
    ("현금흐름표 배당 계정 (cf_dividend_account)", "회사 × 사업연도 × 현금흐름표 배당 계정 1줄(포함·제외 판정)",
     "PK (corp_code, bsns_year, fs_div, ord)"),
]
added = ""
for texts in new_rows:
    r = row
    for o, n in zip(cells_old, texts):
        assert r.count(">" + o + "<") == 1, o
        r = r.replace(">" + o + "<", ">" + escape(n) + "<")
    added += r
x = x[:end] + added + x[end:]

# 2-3. 6.3 D 처리 규칙
sub_text("원 / DART 현금배당총액 기본, KIND·현금흐름표 값과 다르면 병기",
         "원 / DART 현금배당총액 기본, KIND·현금흐름표 값과 다르면 병기. DART 현금배당총액은 백만 원 단위라 "
         "25%·40%·10% 경계 근처는 배당 결정 공시 합계(원 단위 원값)로 재확인 "
         "(공시 합계와 ±1% 일치: 2023 531/536, 2024 558/566, 2025 617/636)")

# 1-4. 6.4 결측 숫자
sub_text("2023 지배주주 순이익 32곳", "2023 지배주주 순이익 1곳(보완 출처는 재무_보완출처 열에 기록)")

# 3. 6.4 품질 점검 항목 추가 (마지막 체크 항목 문단을 복제)
i = x.find("☐ (소급 분석) 예측 시점")
pstart = x.rfind("<w:p ", 0, i)
pend = x.find("</w:p>", i) + len("</w:p>")
para = re.sub(r' w14:(paraId|textId)="[^"]*"', "", x[pstart:pend])
old_t = "☐ (소급 분석) 예측 시점 이후 정보 사용 금지, 학습·검증 기간 분리, 생존 편향 한계 표시"
items = [
    "☐ 재작성 값 vs 최초 보고 값: 2024 부채총계가 02와 04-2에서 19곳 다름(02는 2025 보고서의 전기 재작성 값, "
    "04-2는 2024 보고서의 당기 값). 판정에 어느 쪽을 쓸지 팀 결정 필요",
    "☐ KIND 공시 사업연도 이상: MH머트리얼즈는 12월 결산인데 KIND 공시 사업연도가 2026(배당성향 359.84%)이라 "
    "KIND 대조에서 빠짐. KIND 원문 확인 대상",
    "☐ 2026 귀속 기결의 중간·분기배당: 05에 2026 귀속 공시가 있는 회사 126곳(119곳은 02에 2026 행이 없어 "
    "core_dividend_year에 05만 출처로 행 추가). 6.3 '추가 필요 배당액'의 차감 대상",
    "☐ 원문 못 받은 배당 결정 공시 10건: 케이씨피드, 삼성전기, 오스템, 피에스케이홀딩스, 메타바이오메드, 예스24, "
    "NICE인프라, 테크윙, 팜스빌, SK케미칼",
    "☐ 현금흐름표 배당 계정 상태: 04에서 '정상'이 아닌 행 226건(배당 지급 계정 없음 175, 재무제표 없음 35, "
    "여러 줄 합산 10, 확인필요 계정 있음 6). 이 중 15곳은 배당 계정이 아예 없어 04-1에 없음",
]
assert para.count(old_t) == 1
x = x[:pend] + "".join(para.replace(old_t, escape(t)) for t in items) + x[pend:]

# 작성일에 판 표시
sub_text("2026.10.22", "2026.10.22 (v0.2 수정사항 반영)")

open(path, "w", encoding="utf-8").write(x)
print("ok")
