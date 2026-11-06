"""챗봇 보유 종목 해석 정답률 점검: 실제 Ollama와 회사 목록으로 시험 문장을 해석해 정답과 비교한다.

실행: .venv/bin/python -m scripts.eval_chat_ai [--set design|new] [--no-ai] [--label 이름] [--out 파일]
- 규칙 → (실패하면) AI → 검사, 챗봇과 같은 순서(core.chat_parse.Parser)로 돈다
- 정답: 회사와 주식 수가 모두 맞으면 정답. 목록에 없는 회사 문장은 '거절'이 정답
- 잘못 통과: 검사를 통과했는데 회사나 주식 수가 틀린 경우 (가장 위험한 오류)
- AI 응답은 모델에 따라 달라지므로, 결과에는 모델 이름과 날짜를 함께 적는다
"""
import argparse
from datetime import date
from pathlib import Path

from core import company_repo, llm_ollama
from core.chat_parse import Parser
from core.virtual_cases import COMPANIES as VIRTUAL

REJECT = "거절"
# (고객이 쓴 문장, 정답 [(회사, 주식 수)] 또는 REJECT)
CASES = [
    ("삼성전자 주식을 한 삼백주쯤 갖고 있어요", [("삼성전자", 300)]),
    ("삼성전자 주식 300주", [("삼성전자", 300)]),
    ("삼성전자 300주", [("삼성전자", 300)]),
    ("엘지전자 오십 주요", [("LG전자", 50)]),
    ("LG 전자 50주", [("LG전자", 50)]),
    ("케이티앤지 이백주하고 삼성전기 백주", [("케이티앤지", 200), ("삼성전기", 100)]),
    ("KT&G 200주", [("케이티앤지", 200)]),
    ("씨사 삼백 주", [("C사", 300)]),
    ("C사 3,000주, E사 1,200주", [("C사", 3000), ("E사", 1200)]),
    ("하나금융지주 이천주 있어요", [("하나금융지주", 2000)]),
    ("KB금융 100주랑 신한지주 50주", [("KB금융", 100), ("신한지주", 50)]),
    ("엘지화학 칠십 주", [("LG화학", 70)]),
    ("지에스 삼십주", [("GS", 30)]),
    ("HD현대중공업 25주 들고 있어요", [("HD현대중공업", 25)]),
    ("한미반도체 주식 오백 주 정도", [("한미반도체", 500)]),
    ("POSCO홀딩스 열 주", [("POSCO홀딩스", 10)]),
    ("삼성에스디에스 백오십 주", [("삼성에스디에스", 150)]),
    ("에스케이 가스 사십 주", [("SK가스", 40)]),
    ("애플 10주", REJECT),
    ("SK하이닉스 열 주 있어", REJECT),  # 고배당기업 목록에 없음
]
# 규칙을 고치는 동안 보지 않은 새 문장 (고친 규칙이 위 문장에만 맞춘 것인지 확인용, AI를 거칠 문장 위주)
HELDOUT = [
    ("삼성 전자를 이백 주 정도 갖고 있습니다", [("삼성전자", 200)]),
    ("엘지 유플러스 1천 주", [("LG유플러스", 1000)]),
    ("하나금융 지주 천오백주요", [("하나금융지주", 1500)]),
    ("삼성전자 2백주", [("삼성전자", 200)]),
    ("케이비금융 삼백 주랑 신한지주 이백 주", [("KB금융", 300), ("신한지주", 200)]),
    ("현대글로비스는 육십주 보유 중", [("현대글로비스", 60)]),
    ("에이치디현대 마흔다섯 주", [("HD현대", 45)]),
    ("제가 갖고 있는 건 삼성카드 120주예요", [("삼성카드", 120)]),
    ("에스원 삼백주, 삼성증권 이백주", [("에스원", 300), ("삼성증권", 200)]),
    ("LG 백 주", [("LG", 100)]),
    ("삼성전기를 열다섯 주쯤", [("삼성전기", 15)]),
    ("케이티 오백 주 들고 있어", [("케이티", 500)]),
    ("포스코인터내셔널 사백주", [("포스코인터내셔널", 400)]),
    ("테슬라 5주", REJECT),
    ("카카오 백 주", REJECT),
]
SETS = {"design": CASES, "new": HELDOUT}


def run(use_ai: bool, cases=CASES) -> list[dict]:
    known = company_repo.name_index({**VIRTUAL, **company_repo.load()})
    parser = Parser(known, llm=llm_ollama.get_llm() if use_ai else None)
    rows = []
    for text, want in cases:
        r = parser.holdings(text)
        got = sorted((h.company, h.shares) for h in r.value) if r.ok else REJECT
        expect = REJECT if want == REJECT else sorted(want)
        rows.append({"text": text, "want": expect, "got": got, "by": r.by, "error": r.error,
                     "correct": got == expect, "wrong_pass": r.ok and got != expect})
    return rows


def report(rows: list[dict], label: str) -> str:
    n = len(rows)
    ok = sum(r["correct"] for r in rows)
    wrong = sum(r["wrong_pass"] for r in rows)
    lines = [f"### {label}", "",
             f"정답 {ok}/{n} ({ok / n:.0%}) · 잘못 통과 {wrong}건 · 모델 {llm_ollama.MODEL} · {date.today()}", "",
             "| 문장 | 정답 | 결과 | 해석 | 맞음 |", "|---|---|---|---|---|"]
    fmt = lambda v: v if v == REJECT else ", ".join(f"{c} {s}" for c, s in v)
    for r in rows:
        res = fmt(r["got"]) if r["got"] != REJECT else f"거절 ({r['error']})"
        mark = "○" if r["correct"] else ("✕ 잘못 통과" if r["wrong_pass"] else "✕")
        lines.append(f"| {r['text']} | {fmt(r['want'])} | {res} | {r['by']} | {mark} |")
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="챗봇 보유 종목 해석 정답률")
    ap.add_argument("--no-ai", action="store_true", help="규칙만으로 (AI 끔)")
    ap.add_argument("--label", default="결과")
    ap.add_argument("--set", choices=list(SETS), default="design", help="design: 규칙을 고칠 때 본 문장, new: 보지 않은 새 문장")
    ap.add_argument("--out", type=Path, help="결과 표를 이 마크다운 파일 끝에 덧붙임")
    a = ap.parse_args()
    text = report(run(not a.no_ai, SETS[a.set]), f"{a.label} · {a.set}")
    print(text)
    if a.out:
        with open(a.out, "a", encoding="utf-8") as f:
            f.write(text + "\n\n")
