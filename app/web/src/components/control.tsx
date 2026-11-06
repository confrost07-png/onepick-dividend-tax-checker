// 데이터 이야기 '대조군과 비교' 장 그래프: 고배당기업 중 같은 4개 업종(파랑)과 대조군(회색)을 해마다 나란히. SVG를 직접 그린다.
import { useState } from 'react'

/** rows = [연도, 우리 값, 대조군 값]. 점에 마우스를 올리거나 Tab으로 고르면 두 값이 아래에 뜬다. */
export function TwoLines({ rows, unit, label, xLabel }: { rows: [number, number | null, number | null][]; unit: string; label: string; xLabel?: (y: number) => string }) {
  const W = 640, H = 280, top = 30, bottom = 40, L = 34, R = 90
  const vals = rows.flatMap(r => [r[1], r[2]]).filter((v): v is number => v !== null)
  const hi = Math.max(100, ...vals), lo = 0
  const x = (i: number) => L + i * (W - L - R) / Math.max(rows.length - 1, 1)
  const y = (v: number) => top + (hi - v) / (hi - lo) * (H - top - bottom)
  const path = (k: 1 | 2) => rows.map((r, i) => r[k] === null ? '' : `${i && rows[i - 1][k] !== null ? 'L' : 'M'}${x(i)},${y(r[k]!)}`).join(' ')
  const [tip, setTip] = useState('')
  const show = (v: number | null) => v === null ? '–' : `${v.toFixed(1)}${unit}`
  const last = rows[rows.length - 1]
  return (
    <>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
        {[0, 50, 100].map(g => <g key={g}><line x1={L} x2={W - R} y1={y(g)} y2={y(g)} className="guide" /><text x={L - 6} y={y(g) + 4} className="tick" textAnchor="end">{g}</text></g>)}
        <path d={path(2)} className="line-gray" />
        <path d={path(1)} className="line-sea" />
        {rows.map((r, i) => {
          const text = `${xLabel ? xLabel(r[0]) : r[0]}: 고배당기업(같은 4개 업종) ${show(r[1])} · 대조군 ${show(r[2])}`
          return (
            <g key={r[0]} className="bar" tabIndex={0} aria-label={text} onMouseEnter={() => setTip(text)} onFocus={() => setTip(text)} onMouseLeave={() => setTip('')} onBlur={() => setTip('')}>
              <rect className="hit" x={x(i) - 18} y={top} width={36} height={H - top - bottom} />
              {r[2] !== null && <circle cx={x(i)} cy={y(r[2])} r={6} className="dot-gray" />}
              {r[1] !== null && <circle cx={x(i)} cy={y(r[1])} r={6} className="dot-sea" />}
              <text x={x(i)} y={H - 14} className="tick" textAnchor="middle">{xLabel ? xLabel(r[0]) : String(r[0]).slice(2)}</text>
            </g>
          )
        })}
        {last[1] !== null && <text x={W - R + 12} y={y(last[1]) + 8} className="end-sea">{last[1].toFixed(0)}{unit}</text>}
        {last[2] !== null && <text x={W - R + 12} y={y(last[2]) + 8} className="end-gray">{last[2].toFixed(0)}{unit}</text>}
      </svg>
      <p className="chart-tip" aria-live="polite">{tip || '점에 마우스를 올리면 두 집단 값이 나와요 · 파랑 = 고배당기업(같은 4개 업종), 회색 = 대조군'}</p>
    </>
  )
}

/** rows = [구간, 우리 비율(%), 대조군 비율(%)]. 구간마다 파랑·회색 막대를 나란히 */
export function PairBars({ rows, label }: { rows: [string, number, number][]; label: string }) {
  const W = 640, H = 260, top = 28, bottom = 40, L = 10
  const hi = Math.max(10, ...rows.flatMap(r => [r[1], r[2]]))
  const y = (v: number) => top + (hi - v) / hi * (H - top - bottom)
  const gw = (W - L * 2) / rows.length, bw = Math.min(46, gw / 2 - 10)
  const [tip, setTip] = useState('')
  return (
    <>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
        {rows.map(([name, a, b], i) => {
          const cx = L + gw * i + gw / 2
          const text = `${name}: 고배당기업(같은 4개 업종) ${a.toFixed(1)}% · 대조군 ${b.toFixed(1)}%`
          return (
            <g key={name} className="bar" tabIndex={0} aria-label={text} onMouseEnter={() => setTip(text)} onFocus={() => setTip(text)} onMouseLeave={() => setTip('')} onBlur={() => setTip('')}>
              <rect className="hit" x={cx - gw / 2} y={top} width={gw} height={H - top - bottom} />
              <rect x={cx - bw - 3} y={y(a)} width={bw} height={y(0) - y(a)} rx={4} className="bar-sea" />
              <rect x={cx + 3} y={y(b)} width={bw} height={y(0) - y(b)} rx={4} className="bar-gray" />
              <text x={cx - bw / 2 - 3} y={y(a) - 6} className="soft" textAnchor="middle">{a.toFixed(0)}</text>
              <text x={cx + bw / 2 + 3} y={y(b) - 6} className="soft" textAnchor="middle">{b.toFixed(0)}</text>
              <text x={cx} y={H - 14} className="tick" textAnchor="middle">{name}</text>
            </g>
          )
        })}
        <line x1={L} x2={W - L} y1={y(0)} y2={y(0)} className="axis" />
      </svg>
      <p className="chart-tip" aria-live="polite">{tip || '막대에 마우스를 올리면 두 집단 비율이 나와요 · 파랑 = 고배당기업(같은 4개 업종), 회색 = 대조군'}</p>
    </>
  )
}
