"""고배당기업 요건을 다음 해에도 유지할까 — 과거 유지·탈락 표와 탈락 예측 (분석 설계 B1).

[팀 해석] 과거 판정은 core.p1_analysis.retro_status(지금 판정 엔진, B = D, 제2호 기준선 = 전년 배당)를 쓴다.
y년 숫자로 충족한 회사가 y+1년 숫자로도 충족하는지 본다. 638사는 2025 숫자로 고배당기업이 된 회사만이라
'2024 → 2025' 유지율은 실제보다 높게 나온다. 그래서 예측 모델의 학습·확인에는 결과 연도 2024까지만 쓴다.

예측 특징(y년 기준): 나목으로 충족했나, 배당성향, 배당 증가율, ROE, ROE가 전년보다 얼마나 출렁였나, 부채비율, 적자 여부.
"""
from core.judgement import HOLD, MET
from core.p1_analysis import retro_status

FEATURES = [("나목으로 충족(가목이 아님)", "route_na", 1.0), ("배당성향 10%p 높을 때", "payout", 10.0),
            ("배당 증가율 10%p 높을 때", "d_growth", 10.0), ("ROE 10%p 높을 때", "roe", 10.0),
            ("ROE가 전년보다 10%p 더 출렁일 때", "roe_swing", 10.0), ("부채비율 100%p 높을 때", "debt", 100.0),
            ("적자(배당성향 간주)", "deficit", 1.0)]


def _clip(v, lo, hi):
    return None if v is None else max(lo, min(hi, v))


def _roe(ni: dict, bs: dict, y: int):
    n, (_, eq) = ni.get(y), bs.get(y, (None, None))
    return n * 100 / eq if n is not None and eq and eq > 0 else None


def features(d: dict, ni: dict, bs: dict, y: int) -> dict | None:
    """y년에 충족한 회사의 특징. 충족이 아니거나 값이 모자라면 None."""
    j = retro_status(d, ni, bs, y)
    if j.status != MET:
        return None
    n, dy, dp = ni.get(y), d.get(y), d.get(y - 1)
    liab, eq = bs.get(y, (None, None))
    roe, roe_prev = _roe(ni, bs, y), _roe(ni, bs, y - 1)
    f = {"route_na": float(j.route == "나목"),
         "payout": _clip(dy * 100 / n, 0, 200) if n and n > 0 else 25.0 if j.deemed_payout else None,
         "d_growth": _clip((dy / dp - 1) * 100, -100, 300) if dp else None,
         "roe": _clip(roe, -100, 100),
         "roe_swing": _clip(abs(roe - roe_prev), 0, 100) if roe is not None and roe_prev is not None else None,
         "debt": _clip(liab * 100 / eq, 0, 1000) if liab is not None and eq and eq > 0 else None,
         "deficit": float(n is not None and n <= 0)}
    return None if any(v is None for v in f.values()) else f


def panel(companies: dict, years) -> list[dict]:
    """y년 충족 → y+1년 결과(탈락 1 / 유지 0). y+1이 판정 보류면 뺀다."""
    rows = []
    for corp, (d, ni, bs) in companies.items():
        for y in years:
            f = features(d, ni, bs, y)
            if f is None:
                continue
            nxt = retro_status(d, ni, bs, y + 1)
            if nxt.status == HOLD:
                continue
            rows.append({"corp": corp, "year": y, "drop": float(nxt.status != MET),
                         "reason": (nxt.reasons[0].split(":")[0] if nxt.reasons else "") if nxt.status != MET else "", **f})
    return rows


def auc(scores, labels) -> float:
    """탈락 회사의 점수가 유지 회사보다 높을 확률(0.5 = 동전 던지기, 1 = 완벽). 같은 점수는 반으로 센다."""
    pos = [s for s, l in zip(scores, labels) if l]
    neg = [s for s, l in zip(scores, labels) if not l]
    if not pos or not neg:
        return float("nan")
    wins = sum((p > q) + 0.5 * (p == q) for p in pos for q in neg)
    return wins / (len(pos) * len(neg))
