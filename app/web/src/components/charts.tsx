// 데이터 이야기 그래프. 차트 라이브러리 기본 모양을 쓰지 않고 SVG를 직접 그린다(설계 5절).
// 막대는 마우스를 올리거나 Tab으로 고르면 아래에 설명이 뜬다.
import { useState } from 'react'
import type { Analysis, CurvePoint } from '../api'

function useTip(fallback: string) {
  const [tip, setTip] = useState('')
  const bind = (text: string) => ({
    tabIndex: 0, 'aria-label': text,
    onMouseEnter: () => setTip(text), onFocus: () => setTip(text),
    onMouseLeave: () => setTip(''), onBlur: () => setTip(''),
  })
  const box = <p className="chart-tip" aria-live="polite">{tip || fallback}</p>
  return { bind, box }
}

export function RetroChart({ rows }: { rows: Analysis['retro'] }) {
  const W = 640, B = 250, top = 40, L = 30
  const bw = (W - L - 20) / rows.length
  const { bind, box } = useTip('막대에 마우스를 올리면 자세한 숫자가 나와요')
  const y50 = B - (B - top) * .5
  return (
    <>
      <svg className="chart" viewBox={`0 0 ${W} 300`} role="img" aria-label="다음 해 탈락률 막대 그래프">
        <line x1={L} x2={W - 10} y1={B} y2={B} className="axis" />
        <line x1={L} x2={W - 10} y1={y50} y2={y50} className="guide" />
        <text x={W - 10} y={y50 - 6} className="tick" textAnchor="end">50%</text>
        {rows.map(([year, met, , fail, rate], i) => {
          const h = (B - top) * rate / 100, x = L + i * bw + bw * .18, w = bw * .64
          return (
            <g key={year} className="bar" {...bind(`${year}년 요건을 넘은 ${met}곳 중 ${fail}곳이 다음 해에 떨어졌어요 (${rate}%)`)}>
              <rect className="hit" x={x - 6} y={top} width={w + 12} height={B - top} />
              <rect x={x} y={B - h} width={w} height={h} rx={10} className={year === 2024 ? 'bar-coin' : 'bar-sea'} />
              <text x={x + w / 2} y={B - h - 10} className="val" textAnchor="middle">{rate.toFixed(1)}%</text>
              <text x={x + w / 2} y={B + 22} className="tick" textAnchor="middle">{year}→{year + 1}</text>
              <text x={x + w / 2} y={B + 40} className="tick soft" textAnchor="middle">{fail}/{met}곳</text>
            </g>
          )
        })}
      </svg>
      {box}
    </>
  )
}

const EASY: Record<string, string> = {
  '제2호 미충족': '배당이 전년보다 줄었어요 (제2호)',
  '배당성향 25% 미만': '번 돈의 25%도 배당하지 않았어요',
  '배당성향 25~40%이지만 이익배당금액 10% 증가 미달': '25~40%인데 배당을 10% 이상 늘리지 않았어요',
  '적자로 배당성향 25% 간주, 이익배당금액 10% 증가 미달': '적자라 25%로 보는데, 배당을 10% 이상 늘리지 않았어요',
  '적자이고 부채가 자본총액의 2배 초과': '적자이고 빚이 자본의 2배를 넘었어요',
}

export function ReasonsChart({ rows }: { rows: Analysis['drop_reasons'] }) {
  const W = 1000, rowh = 46, total = rows.reduce((a, [, n]) => a + n, 0), mx = Math.max(...rows.map(r => r[1]))
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${rowh * rows.length + 10}`} role="img" aria-label="다음 해 탈락 이유">
      {rows.map(([label, n], i) => {
        const y = i * rowh + 6, w = Math.max((W - 140) * n / mx, 6)
        return (
          <g key={label}>
            <text x={0} y={y + 12} className="lab">{EASY[label] ?? label}</text>
            <rect x={0} y={y + 18} width={w} height={16} rx={8} className={i === 0 ? 'bar-no' : 'bar-gray'} />
            <text x={w + 10} y={y + 31} className="val">{n}건 · {Math.round(n / total * 100)}%</text>
          </g>
        )
      })}
    </svg>
  )
}

export function PayoutChart({ rows }: { rows: Analysis['payout'] }) {
  const W = 900, B = 270, top = 50, L = 10, mx = Math.max(...rows.map(r => r[1])), bw = (W - L - 10) / rows.length
  const { bind, box } = useTip('막대에 마우스를 올리면 그 구간의 회사 수가 나와요')
  return (
    <>
      <svg className="chart" viewBox={`0 0 ${W} 320`} role="img" aria-label="2025 배당성향 분포">
        {rows.map(([v, n]) => {
          const x = L + (v - 10) * bw + 1.5, h = (B - top) * n / mx
          return (
            <g key={v} className="bar" {...bind(`배당성향 ${v}%대: ${n}곳`)}>
              <rect className="hit" x={x} y={top} width={bw - 3} height={B - top} />
              {n > 0 && <rect x={x} y={B - h} width={bw - 3} height={h} rx={4} className={v === 25 ? 'bar-coin' : v >= 25 ? 'bar-sea' : 'bar-gray'} />}
              {v % 5 === 0 && <text x={x + bw / 2} y={B + 20} className="tick" textAnchor="middle">{v}%</text>}
            </g>
          )
        })}
        {[25, 40].map(v => {
          const x = L + (v - 10) * bw
          return (
            <g key={v} pointerEvents="none">
              <line x1={x} x2={x} y1={top - 20} y2={B} className="thr" />
              <rect x={x - 38} y={top - 42} width={76} height={24} rx={12} className="pill" />
              <text x={x} y={top - 25} className="pill-t" textAnchor="middle">{v}% 기준선</text>
            </g>
          )
        })}
        <line x1={L} x2={W - 10} y1={B} y2={B} className="axis" />
      </svg>
      {box}
    </>
  )
}

const RUNWAY = [
  { cls: 'seg-ok', short: '올해만큼이면 충분' }, { cls: 'seg-coin', short: '10% 안쪽 더' },
  { cls: 'seg-warn', short: '10~25% 더' }, { cls: 'seg-warn2', short: '25~50% 더' }, { cls: 'seg-no', short: '1.5배 넘게' },
]

export function RunwayChart({ rows }: { rows: Analysis['min_ratio'] }) {
  const W = 900, total = rows.reduce((a, [, n]) => a + n, 0)
  const rest = rows.slice(2).reduce((a, [, n]) => a + n, 0)
  const { bind, box } = useTip('칸에 마우스를 올리면 구간 이름과 회사 수가 나와요')
  let x = 0
  return (
    <>
      <svg className="chart" viewBox={`0 0 ${W} 150`} role="img" aria-label="2027년 최소 필요 배당 ÷ 2025년 배당">
        {rows.map(([label, n], i) => {
          const w = W * n / total, x0 = x
          x += w
          const lx = x0 + (w > 60 ? 16 : w / 2)
          return (
            <g key={label} className="bar" {...bind(`${label}: ${n}곳 (${Math.round(n / total * 100)}%)`)}>
              <rect x={x0} y={20} width={Math.max(w - 3, 2)} height={56} rx={14} className={RUNWAY[i]?.cls} />
              {w > 60 && <text x={x0 + 16} y={56} className="seg-n">{n}곳</text>}
              {i < 2 && <><text x={lx} y={104} className="lab">{RUNWAY[i].short}</text><text x={lx} y={124} className="tick">{Math.round(n / total * 100)}%</text></>}
            </g>
          )
        })}
        <text x={W} y={104} className="lab" textAnchor="end">25% 넘게 더 줘야 하는 회사 {rest}곳</text>
        <text x={W} y={124} className="tick" textAnchor="end">{rows.slice(2).map(([, n], i) => `${RUNWAY[i + 2].short} ${n}`).join(' · ')}</text>
      </svg>
      {box}
    </>
  )
}

const CAR_STYLE: Record<string, [string, string]> = {
  '주당배당금 증가': ['sea', '배당을 늘린다는 공시'],
  '주당배당금 유지·감소': ['gray', '배당을 유지·줄인다는 공시'],
}

export function CarChart({ curves }: { curves: Record<string, CurvePoint[]> }) {
  const W = 720, L = 50, R = 190, top = 20, B = 300
  const all = Object.values(curves).flat().flatMap(d => d.slice(2))
  const lo = Math.min(...all, -1) - 1, hi = Math.max(...all) + 1
  const X = (d: number) => L + (W - L - R) * d / 60, Y = (v: number) => B - (B - top) * (v - lo) / (hi - lo)
  const ticks = []
  for (let v = Math.floor(lo / 5) * 5; v <= hi; v += 5) if (v >= lo) ticks.push(v)
  const kinds = Object.keys(CAR_STYLE).filter(k => curves[k])
  // 끝 이름표가 겹치지 않게 아래쪽 이름표를 내린다
  const ends = kinds.map(k => Y(curves[k][curves[k].length - 1][2]))
  const labelY = ends.map((y, i) => (i > 0 && Math.abs(y - ends[0]) < 46 ? ends[0] + (y >= ends[0] ? 46 : -46) : y))
  return (
    <svg className="chart" viewBox={`0 0 ${W} 340`} role="img" aria-label="공시 뒤 60거래일 초과수익률">
      {ticks.map(v => (
        <g key={v}>
          <line x1={L} x2={W - R} y1={Y(v)} y2={Y(v)} className={v === 0 ? 'axis' : 'guide'} />
          <text x={L - 8} y={Y(v) + 4} className="tick" textAnchor="end">{v ? `${v > 0 ? '+' : ''}${v}%p` : '0'}</text>
        </g>
      ))}
      {[0, 20, 40, 60].map(d => <text key={d} x={X(d)} y={B + 24} className="tick" textAnchor="middle">{d}일</text>)}
      {kinds.map(k => {
        const s = curves[k], col = CAR_STYLE[k][0]
        const band = s.map(([d, , , a]) => `${X(d)},${Y(a)}`).concat([...s].reverse().map(([d, , , , b]) => `${X(d)},${Y(b)}`)).join(' ')
        return <polygon key={k} points={band} className={`band-${col}`} />
      })}
      {kinds.map((k, i) => {
        const s = curves[k], [col, name] = CAR_STYLE[k], [d, n, m] = s[s.length - 1], ly = labelY[i]
        return (
          <g key={k}>
            <polyline points={s.map(([d, , m]) => `${X(d)},${Y(m)}`).join(' ')} className={`line-${col}`} />
            <circle cx={X(d)} cy={Y(m)} r={6} className={`dot-${col}`} />
            <text x={X(d) + 14} y={ly - 4} className={`end-${col}`}>{m > 0 ? '+' : ''}{m.toFixed(2)}%p</text>
            <text x={X(d) + 14} y={ly + 16} className="tick">{name} {n}건</text>
          </g>
        )
      })}
    </svg>
  )
}
