// 경기와 배당: 연도별 막대, 뚜렷한 짝 산점도, 상관표. 값은 서버가 저장해 둔 결과(api.ts Macro)를 그대로 쓴다.
import { useState } from 'react'
import type { Macro } from '../api'

const r2 = (v: number | null) => (v === null ? '–' : v.toFixed(2).replace('-', '−'))

/** 연도별 막대. 2025는 동전 색, 음수는 기준선 아래로 */
export function YearBars({ rows, unit, label }: { rows: [number, number | null][]; unit: string; label: string }) {
  const W = 440, H = 220, top = 20, bottom = 32, L = 8
  const vals = rows.map(r => r[1] ?? 0)
  const hi = Math.max(0, ...vals), lo = Math.min(0, ...vals), span = hi - lo || 1
  const y = (v: number) => top + (hi - v) / span * (H - top - bottom)
  const bw = (W - L * 2) / rows.length
  const [tip, setTip] = useState('')
  return (
    <>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
        {rows.map(([yr, v]) => {
          if (v === null) return null
          const x = L + (yr - rows[0][0]) * bw + 4, y0 = y(Math.max(v, 0)), h = Math.abs(y(v) - y(0))
          const text = `${yr}: ${v.toLocaleString('ko-KR', { maximumFractionDigits: 1 })}${unit}`
          return (
            <g key={yr} className="bar" tabIndex={0} aria-label={text} onMouseEnter={() => setTip(text)} onFocus={() => setTip(text)} onMouseLeave={() => setTip('')} onBlur={() => setTip('')}>
              <rect className="hit" x={x} y={top} width={bw - 8} height={H - top - bottom} />
              <rect x={x} y={y0} width={bw - 8} height={Math.max(h, 1)} rx={4} className={yr === 2025 ? 'bar-coin' : 'bar-gray'} />
              <text x={x + (bw - 8) / 2} y={H - 10} className="tick" textAnchor="middle">{String(yr).slice(2)}</text>
            </g>
          )
        })}
        <line x1={L} x2={W - L} y1={y(0)} y2={y(0)} className="axis" />
      </svg>
      <p className="chart-tip" aria-live="polite">{tip || '막대에 마우스를 올리면 값이 나와요'}</p>
    </>
  )
}

const VIEWS: [string, string][] = [['level', '그 해 값끼리'], ['diff', '전년 대비 변화끼리'], ['panel', '회사마다'], ['panel_ex2025', '회사마다 (2025 빼고)']]

/** 시차·보는 법을 고르면 배당 지표 × 거시지표 Spearman 표가 바뀐다. p < 0.05 칸은 진하게 */
export function CorrExplorer({ m }: { m: Macro }) {
  const [lag, setLag] = useState(m.lags[0][0])
  const [view, setView] = useState('diff')
  const rows = m.corr.filter(c => c[0] === lag && c[1] === view)
  const macros = [...new Set(rows.map(c => c[3]))]
  const divs = [...new Set(rows.map(c => c[2]))]
  const cell = (d: string, k: string) => rows.find(c => c[2] === d && c[3] === k)
  const sig = rows.filter(c => c[5] !== null && c[5] < 0.05).length
  return (
    <div className="card">
      <div className="chips" role="group" aria-label="거시 값을 붙인 시점" style={{ marginBottom: 8 }}>
        {m.lags.map(([k, label]) => <button key={k} className="chip" aria-pressed={lag === k} onClick={() => setLag(k)} style={lag === k ? { background: 'var(--sea)', color: '#fff' } : undefined}>{label}</button>)}
      </div>
      <div className="chips" role="group" aria-label="보는 법" style={{ marginBottom: 14 }}>
        {VIEWS.map(([k, label]) => <button key={k} className="chip" aria-pressed={view === k} onClick={() => setView(k)} style={view === k ? { background: 'var(--ink)', color: '#fff' } : undefined}>{label}</button>)}
      </div>
      <div className="corr-table">
        <table>
          <thead><tr><th>배당 \ 거시</th>{macros.map(k => <th key={k}>{m.macro_names[k] ?? k}</th>)}</tr></thead>
          <tbody>
            {divs.map(d => (
              <tr key={d}>
                <th>{m.dividend_names[d] ?? d}</th>
                {macros.map(k => {
                  const c = cell(d, k), r = c?.[4] ?? null, p = c?.[5] ?? null, on = p !== null && p < 0.05
                  return <td key={k} className={on ? (r! > 0 ? 'sig-up' : 'sig-down') : undefined} title={p === null ? '' : `p = ${p.toFixed(3)}`}>{r2(r)}{on && '*'}</td>
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="small" style={{ margin: '10px 0 0' }}>
        이 조합에서 우연이 아닐 수 있는 칸(p &lt; 0.05, *)은 <b>{sig}</b>개 / {rows.length}칸이에요.
        {view !== 'panel' && view !== 'panel_ex2025' && ` 아무 관계가 없어도 ${(rows.length * 0.05).toFixed(1)}칸쯤은 우연히 나와요.`}
        {' '}칸에 마우스를 올리면 p값이 보여요.
      </p>
    </div>
  )
}

const LAG_WORD: Record<string, string> = { same: '같은 해', prev: '1년 전', decision: '결의 시점(이듬해 1~3월)' }
// 회사마다 본 짝은 해마다 모은 값으로 그린다 (회사 하나하나의 점은 수천 개라 겹친다)
const PANEL_YEAR: Record<string, [string, string]> = { dps_up: ['dps_up_share', '주당배당금을 올린 회사 비율'], dps_growth: ['dps_growth_median', '주당배당금 증가율 중앙값'] }

function macroName(m: Macro, k: string) {
  const base = m.macro_names[k] ?? k
  return k.endsWith('_chg') ? `${base} 증감` : base
}

type Pt = { yr: number; x: number; y: number }

/** 산점도 한 칸: 점 하나 = 한 해, 2025는 동전 색, 점선은 대략의 방향(최소제곱) */
function Scatter({ pts, xName, yName, label }: { pts: Pt[]; xName: string; yName: string; label: string }) {
  const W = 320, H = 240, L = 14, R = 14, T = 30, B = 40
  const xs = pts.map(p => p.x), ys = pts.map(p => p.y)
  const pad = (lo: number, hi: number) => { const s = hi - lo || 1; return [lo - s * 0.08, hi + s * 0.08] }
  const [x0, x1] = pad(Math.min(...xs), Math.max(...xs)), [y0, y1] = pad(Math.min(...ys), Math.max(...ys))
  const sx = (v: number) => L + (v - x0) / (x1 - x0) * (W - L - R), sy = (v: number) => T + (y1 - v) / (y1 - y0) * (H - T - B)
  const mx = xs.reduce((a, b) => a + b, 0) / xs.length, my = ys.reduce((a, b) => a + b, 0) / ys.length
  const sxx = xs.reduce((a, v) => a + (v - mx) ** 2, 0), slope = sxx ? pts.reduce((a, p) => a + (p.x - mx) * (p.y - my), 0) / sxx : 0
  const fy = (v: number) => my + slope * (v - mx)
  // 선이 그림 칸(위아래 y0~y1) 밖으로 나가지 않게, y가 칸 안에 드는 x 구간만 그린다
  const [fa, fb] = slope ? [mx + (y0 - my) / slope, mx + (y1 - my) / slope].sort((a, b) => a - b) : [x0, x1]
  const lx0 = Math.max(x0, fa), lx1 = Math.min(x1, fb)
  const [tip, setTip] = useState('')
  const f = (v: number) => v.toLocaleString('ko-KR', { maximumFractionDigits: 2 })
  return (
    <>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
        <line x1={L} x2={W - R} y1={H - B} y2={H - B} className="axis" />
        <line x1={L} x2={L} y1={T} y2={H - B} className="axis" />
        {lx0 < lx1 && <line x1={sx(lx0)} x2={sx(lx1)} y1={sy(fy(lx0))} y2={sy(fy(lx1))} className="fit" />}
        {pts.map(p => {
          const text = `${p.yr}: ${xName} ${f(p.x)} · ${yName} ${f(p.y)}`
          return (
            <g key={p.yr} className="dot" tabIndex={0} aria-label={text} onMouseEnter={() => setTip(text)} onFocus={() => setTip(text)} onMouseLeave={() => setTip('')} onBlur={() => setTip('')}>
              <circle cx={sx(p.x)} cy={sy(p.y)} r={14} fill="transparent" />
              <circle cx={sx(p.x)} cy={sy(p.y)} r={6} className={p.yr === 2025 ? 'bar-coin' : 'bar-sea'} />
              <text x={sx(p.x)} y={sy(p.y) - 10} className="soft" textAnchor="middle">{String(p.yr).slice(2)}</text>
            </g>
          )
        })}
        <text x={W - R} y={H - 12} className="tick" textAnchor="end">{xName} →</text>
        <text x={L} y={4} className="tick" dominantBaseline="hanging">↑ {yName}</text>
      </svg>
      <p className="chart-tip" aria-live="polite">{tip || '점에 마우스를 올리면 그 해 값이 나와요'}</p>
    </>
  )
}

function seriesPts(m: Macro, yKey: string, xKey: string, diff: boolean, drop2025 = false): Pt[] {
  const ys = m.series[yKey] ?? {}, xs = m.series[xKey] ?? {}
  const years = Object.keys(ys).map(Number).sort((a, b) => a - b)
  const val = (s: Record<string, number | null>, yr: number) => {
    const v = s[yr]
    if (v === null || v === undefined) return null
    if (!diff) return v
    const p = s[yr - 1]
    return p === null || p === undefined ? null : v - p
  }
  return years.flatMap(yr => {
    const x = val(xs, yr), y = val(ys, yr)
    return x === null || y === null || (drop2025 && yr === 2025) ? [] : [{ yr, x, y }]
  })
}

const sig = (c: Macro['corr'][number]) => c[5] !== null && c[5] < 0.05
const xKeyOf = (lag: string, macro: string) => (lag === 'same' ? macro : `${macro}@${lag}`)

/** p < 0.05로 뚜렷했던 짝을 모두 산점도로. kinds: 'diff' 변화끼리, 'panel' 회사마다, 'level' 그 해 값끼리 */
export function SigScatters({ m, kind }: { m: Macro; kind: 'diff' | 'panel' | 'level' }) {
  const r = (v: number | null) => r2(v)
  if (kind === 'panel') {
    // 회사마다: 전체·2025 제외 중 한쪽이라도 뚜렷한 짝
    const keys = [...new Set(m.corr.filter(c => (c[1] === 'panel' || c[1] === 'panel_ex2025') && sig(c)).map(c => `${c[0]}|${c[2]}|${c[3]}`))]
    return (
      <div className="scatter-grid">
        {keys.map(k => {
          const [lag, dv, mv] = k.split('|')
          const all = m.corr.find(c => c[0] === lag && c[1] === 'panel' && c[2] === dv && c[3] === mv)
          const ex = m.corr.find(c => c[0] === lag && c[1] === 'panel_ex2025' && c[2] === dv && c[3] === mv)
          const [yKey, yName] = PANEL_YEAR[dv]
          const xName = `${LAG_WORD[lag]} ${macroName(m, mv)}`
          const show = (c: typeof all) => c ? <b className={sig(c) ? (c[4]! > 0 ? 'sig-up' : 'sig-down') : undefined}>{r(c[4])}{sig(c) ? '' : ' (뚜렷하지 않음)'}</b> : '–'
          return (
            <div className="card scatter" key={k}>
              <h4>{yName} ↔ {xName}</h4>
              <p className="small">회사마다 본 상관 {show(all)} · 2025 빼면 {show(ex)} <span>({(all?.[7] ?? 0).toLocaleString('ko-KR')}개 회사·연도)</span></p>
              <Scatter pts={seriesPts(m, yKey, xKeyOf(lag, mv), false)} xName={xName} yName={yName} label={`${yName}과 ${xName}, 해마다`} />
            </div>
          )
        })}
      </div>
    )
  }
  const rows = m.corr.filter(c => c[1] === kind && sig(c)).sort((a, b) => Math.abs(b[4]!) - Math.abs(a[4]!))
  return (
    <div className="scatter-grid">
      {rows.map(c => {
        const [lag, , dv, mv, rv, p] = c
        const xName = `${LAG_WORD[lag]} ${macroName(m, mv)}${kind === 'diff' ? ' 변화' : ''}`
        const yName = `${m.dividend_names[dv] ?? dv}${kind === 'diff' ? ' 변화' : ''}`
        return (
          <div className="card scatter" key={`${lag}${dv}${mv}`}>
            <h4>{yName} ↔ {xName}</h4>
            <p className="small">상관 <b className={rv! > 0 ? 'sig-up' : 'sig-down'}>{r(rv)}</b> · p = {p!.toFixed(3)} · {c[6]}개 해</p>
            <Scatter pts={seriesPts(m, dv, xKeyOf(lag, mv), kind === 'diff')} xName={xName} yName={yName} label={`${yName}과 ${xName}`} />
          </div>
        )
      })}
    </div>
  )
}


/** Benjamini–Hochberg: p값 목록에서 보정 뒤 q < alpha로 남는 개수 */
export function bhCount(ps: number[], alpha = 0.05): number {
  const sorted = [...ps].sort((x, y) => x - y)
  let k = 0
  sorted.forEach((p, i) => { if (p <= alpha * (i + 1) / sorted.length) k = i + 1 })
  return k
}

/** 해마다 계수와 95% 범위(%p). 2025는 동전 색, 기준 해는 속이 빈 점 */
export function CoefChart({ rows, base, label }: { rows: [number, number, number, number][]; base: number; label: string }) {
  const W = 440, H = 230, top = 16, bottom = 30, L = 40, R = 8
  const lo = Math.min(0, ...rows.map(r => r[2])), hi = Math.max(0, ...rows.map(r => r[3])), span = hi - lo || 1
  const y = (v: number) => top + (hi - v) / span * (H - top - bottom)
  const step = (W - L - R) / rows.length
  const x = (i: number) => L + step * (i + 0.5)
  const [tip, setTip] = useState('')
  const pp = (v: number) => `${v > 0 ? '+' : ''}${v.toFixed(1)}%p`.replace('-', '−')
  return (
    <>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
        {[hi, 0, lo].map(v => <text key={v} x={L - 6} y={y(v) + 4} className="soft" textAnchor="end">{v === 0 ? '0' : pp(v)}</text>)}
        <line x1={L} x2={W - R} y1={y(0)} y2={y(0)} className="axis" />
        {rows.map(([yr, c, l, h], i) => {
          const text = yr === base ? `${yr}: 기준 해 (0)` : `${yr}: ${pp(c)} (95% 범위 ${pp(l)} ~ ${pp(h)})`
          return (
            <g key={yr} className="bar" tabIndex={0} aria-label={text} onMouseEnter={() => setTip(text)} onFocus={() => setTip(text)} onMouseLeave={() => setTip('')} onBlur={() => setTip('')}>
              <rect className="hit" x={x(i) - step / 2} y={top} width={step} height={H - top - bottom} />
              {yr !== base && <line x1={x(i)} x2={x(i)} y1={y(h)} y2={y(l)} className="ci" />}
              <circle cx={x(i)} cy={y(c)} r={6} className={yr === base ? 'dot-base' : yr === 2025 ? 'bar-coin' : 'bar-sea'} />
              <text x={x(i)} y={H - 10} className="tick" textAnchor="middle">{String(yr).slice(2)}</text>
            </g>
          )
        })}
      </svg>
      <p className="chart-tip" aria-live="polite">{tip || '점에 마우스를 올리면 값이 나와요'}</p>
    </>
  )
}
