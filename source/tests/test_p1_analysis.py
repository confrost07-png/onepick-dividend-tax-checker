"""F-08 소급 분석·최소액 분포·기준선 몰림 집계 규칙."""
from core import p1_analysis as p

B = 100_000_000


def test_retro_counts_next_year_drop():
    # 2018: 성향 50%(가목 충족) → 2019: 배당이 줄어 제2호(기준선 직전 ≥ 전전) 미충족
    d = {2017: 40 * B, 2018: 50 * B, 2019: 30 * B}
    ni = {2018: 100 * B, 2019: 100 * B}
    df, reasons = p.retro({"x": (d, ni, {})})
    row = df[df["사업연도"] == 2018].iloc[0]
    assert (row["충족"], row["다음 해 판정 가능"], row["다음 해 탈락"], row["탈락률(%)"]) == (1, 1, 1, 100.0)
    assert reasons.iloc[0]["탈락 사유"] == "제2호 미충족"


def test_histogram_and_ratio_bins():
    h = p.histogram([24.9, 25.0, 25.5, 40.2], 20, 45, 1)
    assert dict(zip(h["구간"], h["회사 수"]))[25] == 2 and dict(zip(h["구간"], h["회사 수"]))[24] == 1
    r = p.ratio_bins([90, 100, 105, 200])
    assert list(r["회사 수"]) == [2, 1, 0, 0, 1]
    # 반올림으로 100.0%여도 엔진이 '2025만큼이면 통과 못 함'으로 본 회사는 첫 구간에 넣지 않는다
    r = p.ratio_bins([90, 100, 100, 105], [True, True, False, False])
    assert list(r["회사 수"]) == [2, 2, 0, 0, 0]


def test_threshold_distributions_split_deficit_companies():
    # 적자 회사는 배당성향을 25%(또는 0%)로 간주받으므로 배당성향 그림에서 빼고 수를 따로 세며,
    # 증가율 그림에서는 흑자 회사와 나눠 센다
    comp = {
        "흑자": ({2024: 100 * B, 2025: 110 * B}, {2025: 400 * B}, {}),
        "적자": ({2024: 100 * B, 2025: 110 * B}, {2025: -50 * B}, {2025: (100 * B, 100 * B)}),
        "0원": ({2024: 100 * B, 2025: 120 * B}, {2025: 0}, {}),
        "순이익 모름": ({2024: 100 * B, 2025: 110 * B}, {}, {}),
    }
    payouts, growth, notes = p.threshold_distributions(comp)
    assert payouts == [27.5]
    assert notes["payout_n"] == 1 and notes["deficit_n"] == 2 and notes["growth_n"] == 3
    at10 = growth[growth["구간"] == 10].set_index("구분")["회사 수"]
    assert at10[p.GROUP_PROFIT] == 1 and at10[p.GROUP_DEFICIT] == 1
    assert growth[(growth["구간"] == 20) & (growth["구분"] == p.GROUP_DEFICIT)]["회사 수"].iloc[0] == 1
