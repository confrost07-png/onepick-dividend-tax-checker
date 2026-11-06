"""배당 여력 지도 (분석 설계 B2): '2027년에 얼마나 더 내야 하나' × '그만큼 낼 현금이 있나'로 네 칸에 나눈다.

- 가로: 2027 최소 배당액 ÷ 2025 배당(%). 100%를 넘으면 2025보다 더 내야 한다.
- 세로: 잉여현금흐름(영업현금흐름 − 유형자산 취득) ÷ 2027 최소 배당액(배). 1배보다 작으면 한 해 번 현금으로 모자란다.
  한 해 값은 출렁이므로 2023~2025 평균 잉여현금흐름으로도 본다.
기준선은 판단을 위한 구분일 뿐 합격점이 아니다(F-06 원칙: 합격점은 두지 않음).
"""
import math
from dataclasses import dataclass
from html import escape

SAFE = "충분 · 현금 충분"
TIGHT = "충분 · 현금 빠듯"
ROOM = "더 내야 함 · 현금 충분"
RISK = "더 내야 함 · 현금 부족"
QUADRANTS = (SAFE, TIGHT, ROOM, RISK)


def quadrant(need_pct: float, cover: float) -> str:
    more = need_pct > 100
    cash = cover >= 1
    return (ROOM if cash else RISK) if more else (SAFE if cash else TIGHT)


def average_fcf(ocf: dict[int, float | None], capex: dict[int, float | None], years=(2023, 2024, 2025)) -> float | None:
    """해마다 영업현금흐름 − |유형자산 취득|의 평균. 영업현금흐름이 없는 해는 빼고, 남은 해가 2년 미만이면 None."""
    vals = [ocf[y] - abs(capex.get(y) or 0) for y in years if ocf.get(y) is not None]
    return sum(vals) / len(vals) if len(vals) >= 2 else None


@dataclass(frozen=True)
class Point:
    need_pct: float
    cover: float


Y_TICKS = (-20, -5, -2, -1, 0, 1, 2, 5, 10, 20, 50)


def _symlog(v: float) -> float:
    """0 근처는 거의 그대로, 큰 값은 줄여 보이는 눈금(대칭 로그). 음수 현금 배수도 그릴 수 있다."""
    return math.copysign(math.log10(1 + abs(v)), v)


def svg(points: list[Point], x_range=(40.0, 260.0), y_range=(-20.0, 50.0), width=720, height=460) -> str:
    """네 칸 산점도(정적 SVG). 세로는 대칭 로그 눈금. 범위 밖 점은 가장자리에 붙이고 개수를 적는다. 밝은·어두운 화면 모두 대응."""
    left, right, top, bottom = 64, 24, 28, 56
    pw, ph = width - left - right, height - top - bottom

    def sx(v):
        v = min(max(v, x_range[0]), x_range[1])
        return left + (v - x_range[0]) / (x_range[1] - x_range[0]) * pw

    lo, hi = _symlog(y_range[0]), _symlog(y_range[1])

    def sy(v):
        v = _symlog(min(max(v, y_range[0]), y_range[1]))
        return top + (1 - (v - lo) / (hi - lo)) * ph

    clipped = sum(1 for p in points if not (x_range[0] <= p.need_pct <= x_range[1] and y_range[0] <= p.cover <= y_range[1]))
    counts = {q: sum(1 for p in points if quadrant(p.need_pct, p.cover) == q) for q in QUADRANTS}
    x0, y0 = sx(100), sy(1)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" style="max-width:{width}px" '
           f'role="img" aria-label="배당 여력 지도: 회사 {len(points)}곳">',
           "<style>",
           ".bg{fill:#fcfcfb}.ink{fill:#0b0b0b}.ink2{fill:#52514e}.grid{stroke:#e4e3df;stroke-width:1}"
           ".axis{stroke:#9b9a95;stroke-width:1}.ref{stroke:#52514e;stroke-width:1.5;stroke-dasharray:4 3}"
           ".risk{fill:#eb6834;fill-opacity:.08}.dot{fill:#2a78d6;fill-opacity:.75;stroke:#fcfcfb;stroke-width:2}"
           "text{font-family:-apple-system,'Apple SD Gothic Neo','Noto Sans KR',sans-serif;font-size:12px}"
           ".q{font-size:13px;font-weight:600}",
           "@media (prefers-color-scheme: dark){.bg{fill:#1a1a19}.ink{fill:#f0efec}.ink2{fill:#c3c2b7}"
           ".grid{stroke:#2e2e2c}.axis{stroke:#6b6a66}.ref{stroke:#c3c2b7}.risk{fill:#d95926;fill-opacity:.14}"
           ".dot{fill:#3987e5;stroke:#1a1a19}}",
           "</style>",
           f'<rect class="bg" width="{width}" height="{height}"/>',
           f'<rect class="risk" x="{x0:.1f}" y="{y0:.1f}" width="{left + pw - x0:.1f}" height="{top + ph - y0:.1f}"/>']
    for v in range(int(x_range[0] // 20 * 20) + 20, int(x_range[1]) + 1, 20):
        out.append(f'<line class="grid" x1="{sx(v):.1f}" y1="{top}" x2="{sx(v):.1f}" y2="{top + ph}"/>')
        out.append(f'<text class="ink2" x="{sx(v):.1f}" y="{top + ph + 18}" text-anchor="middle">{v}%</text>')
    for v in (t for t in Y_TICKS if y_range[0] <= t <= y_range[1]):
        out.append(f'<line class="grid" x1="{left}" y1="{sy(v):.1f}" x2="{left + pw}" y2="{sy(v):.1f}"/>')
        out.append(f'<text class="ink2" x="{left - 8}" y="{sy(v) + 4:.1f}" text-anchor="end">{v}배</text>')
    out.append(f'<line class="axis" x1="{left}" y1="{top + ph}" x2="{left + pw}" y2="{top + ph}"/>')
    out.append(f'<line class="ref" x1="{x0:.1f}" y1="{top}" x2="{x0:.1f}" y2="{top + ph}"/>')
    out.append(f'<line class="ref" x1="{left}" y1="{y0:.1f}" x2="{left + pw}" y2="{y0:.1f}"/>')
    for p in points:
        out.append(f'<circle class="dot" cx="{sx(p.need_pct):.1f}" cy="{sy(p.cover):.1f}" r="4">'
                   f'<title>{p.need_pct:.0f}% · {p.cover:.2f}배</title></circle>')
    labels = [(SAFE, left + 8, top + 18, "start"), (ROOM, left + pw - 8, top + 18, "end"),
              (TIGHT, left + 8, top + ph - 10, "start"), (RISK, left + pw - 8, top + ph - 10, "end")]
    for q, x, y, anchor in labels:
        out.append(f'<text class="ink q" x="{x}" y="{y}" text-anchor="{anchor}">{escape(q)} {counts[q]}곳</text>')
    out.append(f'<text class="ink2" x="{left + pw / 2:.1f}" y="{height - 12}" text-anchor="middle">'
               f'2027 최소 배당액 ÷ 2025 배당 (100% 넘으면 더 내야 함)</text>')
    out.append(f'<text class="ink2" transform="translate(16 {top + ph / 2:.1f}) rotate(-90)" text-anchor="middle">'
               f'잉여현금흐름 ÷ 2027 최소 배당액</text>')
    if clipped:
        out.append(f'<text class="ink2" x="{left + pw}" y="{top - 10}" text-anchor="end">범위 밖 {clipped}곳은 가장자리에 표시</text>')
    out.append("</svg>")
    return "\n".join(out)
