// 금액 구간별 세율 한눈에 (/isa-irp): 종합소득세 · 고배당 분리과세 · ISA · IRP를 같은 줄에 놓고 색 진하기로 비교한다.
// 숫자는 /api/isa-irp의 rate_table(core.isa_irp.rate_table → core.tax_rates)에서 받는다. 화면에서는 고르기·말풍선만 한다.
import { useState } from 'react'
import type { RateTable } from '../api'
import { moaSrc } from '../util'

const pct = (permil: number) => `${(permil / 10).toFixed(1)}%`
const manEok = (n: number) => n >= 1e8
  ? `${(n / 1e8).toLocaleString('ko-KR', { maximumFractionDigits: 1 })}억`
  : `${(n / 1e4).toLocaleString('ko-KR')}만`
const rangeLabel = (lo: number, hi: number | null) =>
  hi === null ? `${manEok(lo)} 초과` : lo === 0 ? `${manEok(hi)} 이하` : `${manEok(lo)}~${manEok(hi)}`

// 0% → 연한 파랑(wave), 25% → sea, 50% → 짙은 남색
const STOPS: [number, [number, number, number]][] = [[0, [238, 242, 255]], [0.5, [61, 107, 255]], [1, [20, 33, 107]]]
function heat(permil: number) {
  const t = Math.min(1, permil / 500)
  const i = t <= STOPS[1][0] ? 0 : 1
  const [a, ca] = STOPS[i], [b, cb] = STOPS[i + 1]
  const k = (t - a) / (b - a)
  const c = ca.map((v, j) => Math.round(v + (cb[j] - v) * k))
  return { background: `rgb(${c.join(',')})`, color: t > 0.42 ? '#fff' : 'var(--ink)' }
}
const weight = (permil: number) => permil < 100 ? '🪶' : permil < 200 ? '🎒' : permil < 300 ? '🧳' : permil < 450 ? '🏋️' : '🪨'

export default function RateHeat({ t }: { t: RateTable }) {
  const [at, setAt] = useState(4)
  const row = t.rows[at]
  const gap = row.basic_permil - row.separate_permil
  const n = t.rows.length

  return (
    <div className="rh">
      <div className="rh-pick">
        <img src={moaSrc(gap > 0 ? 'base' : 'curious')} alt="" />
        <div className="rh-bubble" aria-live="polite">
          <b>{rangeLabel(row.lower, row.upper)} 구간이라면</b>
          <p>여기서 더 버는 <strong>1만 원</strong>마다 떼는 세금이 종합소득세는 <strong>{(row.basic_permil * 10).toLocaleString('ko-KR')}원</strong>, 고배당 분리과세는 <strong>{(row.separate_permil * 10).toLocaleString('ko-KR')}원</strong>이에요.</p>
          <p className="small">{gap > 0
            ? `두 세율 차이는 ${pct(gap)}p예요. 분리과세는 요건을 채운 회사의 현금배당에만 쓸 수 있어요.`
            : `이 구간은 종합소득세 세율이 더 낮아요. 그런데 금융소득이 ${manEok(t.threshold)} 원 이하면 종합과세 없이 원천징수 ${pct(t.normal_permil)}로 끝나요.`}</p>
          <label className="rh-slider">
            <span>금액 움직여 보기</span>
            <input type="range" min={0} max={n - 1} value={at} onChange={e => setAt(Number(e.target.value))}
              aria-valuetext={rangeLabel(row.lower, row.upper)} />
          </label>
        </div>
      </div>

      <div className="rh-scroll">
        <div className="rh-grid" role="table" aria-label="금액 구간별 세율 비교 (지방소득세 포함)" style={{ gridTemplateRows: `auto repeat(${n}, 52px)` }}>
          <div className="rh-head rh-corner" role="columnheader">금액 구간</div>
          <div className="rh-head" role="columnheader"><b>종합소득세</b><span>과세표준 · 한계세율</span></div>
          <div className="rh-head" role="columnheader"><b>고배당 분리과세</b><span>고배당기업 배당액</span></div>
          <div className="rh-head" role="columnheader"><b>ISA</b><span>계좌 안 순이익</span></div>
          <div className="rh-head" role="columnheader"><b>IRP 연금으로 받기</b><span>1년 사적연금 수령액</span></div>

          {t.rows.map((r, i) => (
            <div key={r.lower} className={`rh-row${i === at ? ' on' : ''}`} role="row">
              <button type="button" className="rh-label" role="rowheader" style={{ gridRow: i + 2 }} onClick={() => setAt(i)} aria-pressed={i === at}>
                <span aria-hidden="true">{weight(r.basic_permil)}</span>{rangeLabel(r.lower, r.upper)}
              </button>
              <button type="button" className="rh-cell" role="cell" style={{ ...heat(r.basic_permil), gridRow: i + 2, gridColumn: 2 }} onClick={() => setAt(i)}>{pct(r.basic_permil)}</button>
              <button type="button" className="rh-cell" role="cell" style={{ ...heat(r.separate_permil), gridRow: i + 2, gridColumn: 3 }} onClick={() => setAt(i)}>{pct(r.separate_permil)}</button>
            </div>
          ))}

          <div className="rh-tall" role="cell" style={{ ...heat(t.isa.over_permil), gridColumn: 4, gridRow: `2 / span ${n}` }}>
            <strong>{pct(t.isa.over_permil)}</strong>
            <span>순이익 {manEok(t.isa.free_general)} 원까지 0원<br />(서민형 {manEok(t.isa.free_low_income)} 원)<br />넘는 부분은 금액과 상관없이 {pct(t.isa.over_permil)}</span>
            <em>🧺 바구니 안에는 계단이 없어요</em>
          </div>
          <div className="rh-tall rh-tall--top" role="cell" style={{ ...heat(t.irp.pension_permil[1]), gridColumn: 5, gridRow: 2 }}>
            <strong>{pct(t.irp.pension_permil[0])}~{pct(t.irp.pension_permil[1])}</strong>
            <span>1년 {manEok(t.irp.separate_cap)} 원 이하 · 나이별</span>
          </div>
          <div className="rh-tall" role="cell" style={{ ...heat(t.irp.over_permil), gridColumn: 5, gridRow: `3 / span ${n - 1}` }}>
            <strong>{pct(t.irp.over_permil)}</strong>
            <span>1년 {manEok(t.irp.separate_cap)} 원을 넘으면<br />{pct(t.irp.over_permil)} 분리과세 또는<br />종합과세 중 골라요</span>
            <em>⏳ 55세 전에 깨면 {pct(t.irp.early_permil)}</em>
          </div>
        </div>
      </div>

      <div className="rh-legend" aria-hidden="true"><span>0%</span><i /><span>50%</span></div>
      <ul className="rh-notes small">
        <li>같은 줄이라도 재는 돈이 달라요. 종합소득세는 모든 종합소득을 더해 공제한 과세표준, 고배당 분리과세는 요건을 채운 회사에서 받은 현금배당액(ETF·펀드 제외), ISA는 계좌 안 순이익, IRP는 1년 연금 수령액 기준이에요.</li>
        <li>누진세율은 그 구간을 넘는 부분에만 붙어요. 금융소득이 {manEok(t.threshold)} 원 이하면 종합과세 없이 원천징수 {pct(t.normal_permil)}로 끝나요.</li>
        <li>세율은 모두 지방소득세를 포함했어요. 세액 계산 예시이고, 어느 쪽을 고르라는 권유가 아니에요. 근거: {t.source}</li>
      </ul>
    </div>
  )
}
