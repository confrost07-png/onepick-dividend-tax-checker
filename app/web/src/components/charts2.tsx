// 데이터 이야기 추가 그래프: 증가율 기준선, 8년 움직이는 산점도, 공시 뒤 주가 탐색, 최대주주 지분, 재무 여력.
import { useEffect, useMemo, useRef, useState } from 'react'
import type { Analysis, CurvePoint, Events, EventSummary, Movement, Status } from '../api'

/** 증가율 분포: 10% 기준선 (나목) */
export function GrowthChart({ rows }: { rows: Analysis['growth'] }) {
  const W = 900, B = 270, top = 50, L = 10, mx = Math.max(...rows.map(r => r[1])), lo = rows[0][0]
  const bw = (W - L - 10) / rows.length
  const [tip, setTip] = useState('')
  const capped = Math.min(mx, 40) // '0%(전년과 같음)' 막대가 너무 높아 나머지가 안 보이므로 위를 자른다
  return (
    <>
      <svg className="chart" viewBox={`0 0 ${W} 320`} role="img" aria-label="2025 이익배당금액 증가율 분포">
        {rows.map(([v, n]) => {
          const x = L + (v - lo) * bw + 1.5, h = (B - top) * Math.min(n, capped) / capped
          const text = `증가율 ${v}%대: ${n}곳${n > capped ? ' (막대 위를 잘랐어요)' : ''}`
          return (
            <g key={v} className="bar" tabIndex={0} aria-label={text} onMouseEnter={() => setTip(text)} onFocus={() => setTip(text)} onMouseLeave={() => setTip('')} onBlur={() => setTip('')}>
              <rect className="hit" x={x} y={top} width={bw - 3} height={B - top} />
              {n > 0 && <rect x={x} y={B - h} width={bw - 3} height={h} rx={4} className={v === 10 ? 'bar-coin' : v >= 10 ? 'bar-sea' : 'bar-gray'} />}
              {n > capped && <text x={x + bw / 2} y={top - 6} className="val" textAnchor="middle">{n}↑</text>}
              {v % 5 === 0 && <text x={x + bw / 2} y={B + 20} className="tick" textAnchor="middle">{v}%</text>}
            </g>
          )
        })}
        <g pointerEvents="none">
          <line x1={L + (10 - lo) * bw} x2={L + (10 - lo) * bw} y1={top - 20} y2={B} className="thr" />
          <rect x={L + (10 - lo) * bw - 38} y={top - 42} width={76} height={24} rx={12} className="pill" />
          <text x={L + (10 - lo) * bw} y={top - 25} className="pill-t" textAnchor="middle">10% 기준선</text>
        </g>
        <line x1={L} x2={W - 10} y1={B} y2={B} className="axis" />
      </svg>
      <p className="chart-tip" aria-live="polite">{tip || '막대에 마우스를 올리면 그 구간의 회사 수가 나와요'}</p>
    </>
  )
}

const DOT: Record<Status, string> = { '충족': '#3D6BFF', '미충족': '#F2555A', '판정 보류': '#8B95A5' }

/** 8년 움직이는 산점도: 해마다 점이 움직인다. 점 하나 = 회사 하나(이름 없음). */
export function MovingScatter({ data }: { data: Movement }) {
  const years = Object.keys(data.frames).map(Number).sort()
  const [i, setI] = useState(0)
  const [playing, setPlaying] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const W = 900, H = 460, L = 56, R = 20, T = 20, B = 400
  const X = (v: number) => L + (W - L - R) * Math.max(0, Math.min(100, v)) / 100
  const Y = (v: number) => B - (B - T) * (Math.max(-50, Math.min(100, v)) + 50) / 150

  useEffect(() => {
    if (!playing) return
    if (i >= years.length - 1) { setPlaying(false); return }
    const t = setTimeout(() => setI(i + 1), 1100)
    return () => clearTimeout(t)
  }, [playing, i, years.length])
  useEffect(() => { // 화면에 들어오면 한 번 저절로 재생
    const ob = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { setI(0); setPlaying(true); ob.disconnect() } }), { threshold: .5 })
    if (box.current) ob.observe(box.current)
    return () => ob.disconnect()
  }, [])

  const year = years[i]
  const pts = data.frames[String(year)] ?? []
  const near25 = pts.filter(p => p[1] >= 25 && p[1] < 27).length
  const below25 = pts.filter(p => p[1] >= 23 && p[1] < 25).length
  return (
    <div ref={box}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 8 }}>
        <span className="round" style={{ fontSize: 44, lineHeight: 1, color: 'var(--sea)' }}>{year}</span>
        <span className="small" style={{ fontWeight: 800 }}>사업연도 · {pts.length}곳</span>
        <span className="badge badge--hold">25~26%대 {near25}곳 · 23~24%대 {below25}곳</span>
        <button className="btn btn--sm" style={{ marginLeft: 'auto' }} onClick={() => { if (i >= years.length - 1) setI(0); setPlaying(!playing) }}>{playing ? '❚❚ 멈춤' : '▶ 재생'}</button>
      </div>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${year}년 배당성향과 배당 증가율 산점도, ${pts.length}곳`}>
        <rect x={X(40)} y={T} width={X(100) - X(40)} height={B - T} fill="rgba(61,107,255,.06)" />
        <rect x={X(25)} y={T} width={X(40) - X(25)} height={Y(10) - T} fill="rgba(255,201,60,.14)" />
        {[0, 25, 40, 60, 80, 100].map(v => <text key={v} x={X(v)} y={B + 22} className="tick" textAnchor="middle">{v}%</text>)}
        {[-50, 0, 10, 50, 100].map(v => <text key={v} x={L - 8} y={Y(v) + 4} className="tick" textAnchor="end">{v}%</text>)}
        <line x1={L} x2={W - R} y1={Y(0)} y2={Y(0)} className="axis" />
        <line x1={X(25)} x2={X(25)} y1={T} y2={B} className="thr" />
        <line x1={X(40)} x2={X(40)} y1={T} y2={B} className="thr" />
        <line x1={X(25)} x2={X(40)} y1={Y(10)} y2={Y(10)} className="thr" />
        <text x={X(70)} y={T + 22} className="lab" textAnchor="middle" fill="var(--sea-deep)">가목 땅 (40% 이상)</text>
        <text x={X(32.5)} y={T + 22} className="tick" textAnchor="middle">나목 땅</text>
        <text x={(L + W - R) / 2} y={H - 4} className="tick" textAnchor="middle">배당성향 (이익배당금액 ÷ 지배주주 순이익) →</text>
        {pts.map(([id, x, y, s]) => (
          <circle key={id} r={4.5} fill={s ? DOT[s] : '#8B95A5'} opacity={.7} stroke="#fff" strokeWidth={.8}
            style={{ transform: `translate(${X(x)}px, ${Y(y)}px)`, transition: 'transform .9s cubic-bezier(.3,.8,.3,1)' }} />
        ))}
      </svg>
      <input type="range" min={0} max={years.length - 1} value={i} onChange={e => { setPlaying(false); setI(Number(e.target.value)) }} aria-label="사업연도 고르기" style={{ width: '100%' }} />
      <div style={{ display: 'flex', justifyContent: 'space-between' }} className="small">{years.map(y => <span key={y}>{y}</span>)}</div>
    </div>
  )
}

const KIND_ORDER = ['주당배당금 증가', '주당배당금 유지·감소', '무상증자', '유상증자(제3자배정)', '유상증자(주주배정)', '감자(자기주식 소각)', '주식분할']

/** 공시 뒤 주가 반응 탐색: 공시 종류·기간·기준일·수익률·표본을 고르면 곡선과 검정 결과가 바뀐다. */
export function EventExplorer({ ev }: { ev: Events }) {
  const kinds = KIND_ORDER.filter(k => ev.summary.some(s => s.kind === k))
  const [kind, setKind] = useState(kinds[0])
  const [win, setWin] = useState(60)
  const [basis, setBasis] = useState('공시일')
  const [ret, setRet] = useState('배당 포함')
  const [sample, setSample] = useState('자본 변동 겹침 제외')
  const has = (k: string, w: number, b: string, r: string, s: string) => ev.summary.some(x => x.kind === k && x.window === w && x.basis === b && x.ret === r && x.sample === s)
  // 고른 조건이 없으면 가능한 값으로 맞춘다 (증자·감자는 공시일·주가만만 있음)
  const pick = useMemo(() => {
    // 고른 조건과 가장 많이 맞는 것: 기간 > 표본 > 기준일 > 수익률 순으로 중요하게 본다
    const score = (x: EventSummary) => (x.window === win ? 8 : 0) + (x.sample === sample ? 4 : 0) + (x.basis === basis ? 2 : 0) + (x.ret === ret ? 1 : 0)
    return ev.summary.filter(x => x.kind === kind).sort((a, b) => score(b) - score(a))[0]
  }, [ev, kind, win, basis, ret, sample])
  const key = pick ? [pick.kind, pick.basis, pick.ret, pick.sample, pick.window].join('|') : ''
  const curve = ev.curves[key]
  const test = pick?.sample !== '자본 변동 겹침 제외' ? undefined : ev.methods?.tests.find(t => t['공시 종류'] === pick?.kind && t['기준일'] === pick?.basis && t['창'] === pick?.window && t['모형'] === '시장조정' && t['수익률'] === pick?.ret)
  const q = test?.['KP p BH 보정 q'] as number | null | undefined

  const Chip = ({ label, on, ok, set }: { label: string; on: boolean; ok: boolean; set: () => void }) => (
    <button className="chip" onClick={set} disabled={!ok} aria-pressed={on} style={on ? { background: 'var(--sea)', color: '#fff' } : ok ? undefined : { opacity: .35 }}>{label}</button>
  )
  return (
    <div>
      <div className="card ev-pick">
        {([
          ['① 어떤 공시', '어떤 소식이 나온 뒤를 볼까요', '공시 종류', kinds.map(k => <Chip key={k} label={k} on={pick?.kind === k} ok set={() => setKind(k)} />)],
          ['② 얼마 동안', '기준일부터 며칠 뒤까지', '기간', [20, 60].map(w => <Chip key={w} label={`${w}거래일`} on={pick?.window === w} ok={ev.summary.some(x => x.kind === kind && x.window === w)} set={() => setWin(w)} />)],
          ['③ 언제부터', '0일로 잡는 날', '기준일', ['공시일', '주주총회 결의일', '배당락일'].map(b => <Chip key={b} label={b} on={pick?.basis === b} ok={ev.summary.some(x => x.kind === kind && x.basis === b)} set={() => setBasis(b)} />)],
          ['④ 무엇을 셀지', '배당금도 수익에 넣을까요', '수익률', ['배당 포함', '주가만'].map(r => <Chip key={r} label={r} on={pick?.ret === r} ok={ev.summary.some(x => x.kind === kind && x.ret === r)} set={() => setRet(r)} />)],
          ['⑤ 어떤 사례', '증자·감자가 같은 기간에 겹친 회사', '표본', ['자본 변동 겹침 제외', '전체'].map(s => <Chip key={s} label={s} on={pick?.sample === s} ok={!!pick && has(kind, pick.window, pick.basis, pick.ret, s)} set={() => setSample(s)} />)],
        ] as const).map(([title, sub, aria, chips]) => (
          <div className="ev-row" key={title}>
            <div className="ev-q"><b>{title}</b><span>{sub}</span></div>
            <div className="chips" role="group" aria-label={aria}>{chips}</div>
          </div>
        ))}
        {pick && <p className="ev-now">지금 보는 것: <b>{pick.kind}</b> 공시 뒤 · <b>{pick.basis}</b>부터 <b>{pick.window}거래일</b> · <b>{pick.ret === '배당 포함' ? '배당 포함' : '주가만'}</b> 수익률 · {pick.sample === '전체' ? <>증자·감자가 <b>겹친 사례도 모두 넣고</b></> : <>증자·감자가 <b>겹친 사례는 빼고</b></>}</p>}
      </div>
      <div className="ch-body">
        <div className="card">{curve ? <OneCurve curve={curve} days={pick!.window} /> : <p className="small">사례가 10건 미만이라 곡선을 표시하지 않아요.</p>}</div>
        {pick && (
          <div className="ch-side">
            <div className="stat"><b className="num" style={{ color: pick.median >= 0 ? 'var(--sea)' : 'var(--no)' }}>{pick.median > 0 ? '+' : ''}{pick.median.toFixed(2)}%p</b>
              <span>{pick.window}거래일 가운데 값 · {pick.n}건<br />가운데 절반: {pick.p25}~{pick.p75}%p</span></div>
            <div className="stat">
              <span>평균이 0과 다른 게 우연일 가능성{test ? ` · 평균 ${(test['평균(%p)'] as number) > 0 ? '+' : ''}${test['평균(%p)']}%p, ${test['사례']}건` : ''}</span>
              <b style={{ fontSize: 28, marginTop: 4 }}>{q == null ? '검정 안 함' : q < 0.05 ? '우연이라 보기 어려워요' : '우연일 수도 있어요'}</b>
              <span>{q == null ? pick.sample === '전체' ? "검정은 '자본 변동 겹침 제외' 표본으로만 했어요" : '사례가 적어 검정하지 않았어요' : `q ${q < 0.0001 ? '< 0.0001' : '= ' + q.toFixed(4)} (0.05보다 ${q < 0.05 ? '작음' : '큼'})`}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function OneCurve({ curve, days }: { curve: CurvePoint[]; days: number }) {
  const W = 720, L = 50, R = 20, top = 20, B = 300
  const vals = curve.flatMap(d => d.slice(2))
  const lo = Math.min(...vals, -1) - 1, hi = Math.max(...vals, 1) + 1
  const X = (d: number) => L + (W - L - R) * d / days, Y = (v: number) => B - (B - top) * (v - lo) / (hi - lo)
  const step = hi - lo > 40 ? 10 : 5
  const ticks: number[] = []
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) ticks.push(v)
  const last = curve[curve.length - 1]
  return (
    <svg className="chart" viewBox={`0 0 ${W} 340`} role="img" aria-label={`공시 뒤 ${days}거래일 초과수익률 곡선`}>
      {ticks.map(v => (
        <g key={v}>
          <line x1={L} x2={W - R} y1={Y(v)} y2={Y(v)} className={v === 0 ? 'axis' : 'guide'} />
          <text x={L - 8} y={Y(v) + 4} className="tick" textAnchor="end">{v ? `${v > 0 ? '+' : ''}${v}%p` : '0'}</text>
        </g>
      ))}
      {[0, days / 2, days].map(d => <text key={d} x={X(d)} y={B + 24} className="tick" textAnchor="middle">{d}일</text>)}
      <polygon className="band-sea" points={curve.map(([d, , , a]) => `${X(d)},${Y(a)}`).concat([...curve].reverse().map(([d, , , , b]) => `${X(d)},${Y(b)}`)).join(' ')} />
      <polyline className="line-sea" points={curve.map(([d, , m]) => `${X(d)},${Y(m)}`).join(' ')} />
      <circle cx={X(last[0])} cy={Y(last[2])} r={6} className="dot-sea" />
    </svg>
  )
}

/** 최대주주 지분: 기준선 근처 묶음과 나머지의 지분율 가운데 값과 가운데 절반 범위 */
export function HolderChart({ h }: { h: NonNullable<Analysis['holder']> }) {
  const rows = h.table.filter(r => r.표시)
  const W = 900, rowh = 58, L = 230, R = 170, lo = 20, hi = 70
  const X = (v: number) => L + (W - L - R) * (v - lo) / (hi - lo)
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${rowh * rows.length + 40}`} role="img" aria-label="최대주주 지분율 비교">
      {[20, 30, 40, 50, 60, 70].map(v => (
        <g key={v}><line x1={X(v)} x2={X(v)} y1={10} y2={rowh * rows.length} className="guide" />
          <text x={X(v)} y={rowh * rows.length + 22} className="tick" textAnchor="middle">{v}%</text></g>
      ))}
      <text x={W - R + 20} y={18} className="tick">개인 최대주주</text>
      {rows.map((r, i) => {
        const y = i * rowh + 34, far = r.묶음.startsWith('나머지')
        return (
          <g key={r.묶음}>
            <text x={0} y={y + 5} className="lab">{r.묶음}</text>
            <text x={0} y={y + 23} className="tick">{r['회사 수']}곳</text>
            <rect x={X(r['1사분위'])} y={y - 7} width={X(r['3사분위']) - X(r['1사분위'])} height={14} rx={7} className={far ? 'bar-gray' : 'bar-coin'} opacity={.7} />
            <circle cx={X(r.중앙값)} cy={y} r={8} className={far ? 'dot-gray' : 'dot-sea'} />
            <text x={X(r.중앙값)} y={y - 14} className="val" textAnchor="middle">{r.중앙값}%</text>
            <text x={W - R + 20} y={y + 6} className={far ? 'end-gray' : 'end-sea'}>{r['개인 최대주주(%)']}%</text>
          </g>
        )
      })}
    </svg>
  )
}

/** 재무 여력: 2025 잉여현금흐름이 2027 최소 필요 배당의 몇 배인가 */
export function CapacityChart({ c }: { c: Analysis['capacity'] }) {
  const W = 900, total = c.bins.reduce((a, [, n]) => a + n, 0), cls = ['seg-no', 'seg-warn', 'seg-coin', 'seg-ok']
  let x = 0
  return (
    <svg className="chart" viewBox={`0 0 ${W} 200`} role="img" aria-label="재무 여력 분포">
      {c.bins.map(([name, n], i) => {
        const w = W * n / total, x0 = x
        x += w
        return (
          <g key={name}>
            <rect x={x0} y={10} width={Math.max(w - 3, 2)} height={56} rx={14} className={cls[i]} />
            {w > 70 && <text x={x0 + 16} y={46} className="seg-n">{n}곳</text>}
            <text x={x0 + 4} y={92} className="lab">{name}</text>
            <text x={x0 + 4} y={112} className="tick">{Math.round(n / total * 100)}%</text>
          </g>
        )
      })}
      {(() => {  // 1배 미만 = 번 현금만으로 모자람, 1배 이상 = 충분함
        const short = c.bins[0][1], wShort = W * short / total
        const groups: [string, number, number, number, string][] = [
          ['배당하기 어려워요', 0, wShort - 3, short, 'var(--no)'],
          ['배당하기 충분해요', wShort, W - 3, total - short, 'var(--sea)'],
        ]
        return groups.map(([name, x0, x1, n, color]) => (
          <g key={name}>
            <path d={`M${x0 + 1},150 V136 H${x1 - 1} V150`} fill="none" stroke={color} strokeWidth={2.5} />
            <text x={(x0 + x1) / 2} y={162} className="lab" textAnchor="middle" style={{ fill: color }}>{name}</text>
            <text x={(x0 + x1) / 2} y={184} className="tick" textAnchor="middle">{n}곳 · {Math.round(n / total * 100)}%</text>
          </g>
        ))
      })()}
    </svg>
  )
}

/** 3장 칸 그림: 배당성향 3구간 × 배당 증가율 3구간에 회사 수·비율·막대. 초록 테두리는 요건을 채우는 칸(가목 2칸 + 나목 1칸).
 *  산점도(MovingScatter)보다 읽기 쉽게 바꾼 것. 마지막 해는 그해 숫자로 회사를 골랐으니 경고를 띄운다. */
const GRID_ROWS = ['배당 10% 이상 증가', '0~10% 증가', '배당 감소']
const GRID_COLS: [string, string][] = [['배당성향', '25% 미만'], ['25~40%', '(나목 땅)'], ['40% 이상', '(가목 땅)']]
const GRID_OK = [[0, 1], [0, 2], [1, 2]]
export function GridChart({ grid }: { grid: Movement['grid'] }) {
  const years = Object.keys(grid).map(Number).sort()
  const last = years[years.length - 1]
  const [y, setY] = useState(last)
  const [playing, setPlaying] = useState(false)
  const total = (g: number[][]) => g.flat().reduce((a, b) => a + b, 0)
  const okPct = (g: number[][]) => (GRID_OK.reduce((s, [r, c]) => s + g[r][c], 0) / Math.max(1, total(g))) * 100
  useEffect(() => {
    if (!playing) return
    const k = years.indexOf(y)
    if (k >= years.length - 1) { setPlaying(false); return }
    const t = setTimeout(() => setY(years[k + 1]), 1200)
    return () => clearTimeout(t)
  }, [playing, y, years])
  const g = grid[y]
  if (!g) return null
  const tot = total(g), mx = Math.max(1, ...g.flat())
  return (
    <div className="g3">
      <div className="g3-top">
        <b className="g3-year">{y}</b>
        <span className="small">사업연도 · {tot.toLocaleString('ko-KR')}곳 · 요건 칸 {okPct(g).toFixed(1)}%</span>
        <span style={{ flex: 1 }} />
        <button className="btn btn--sm" onClick={() => { if (playing) { setPlaying(false); return } setY(years[0]); setPlaying(true) }}>{playing ? '❚❚ 멈춤' : '▶ 재생'}</button>
      </div>
      <div className="g3-years" role="group" aria-label="연도 고르기">
        {years.map(v => (
          <button key={v} className={v === y ? 'on' : ''} aria-pressed={v === y} onClick={() => { setPlaying(false); setY(v) }}>
            {v}<small>{okPct(grid[v]).toFixed(0)}%</small>
          </button>
        ))}
      </div>
      {y === last && <p className="g3-warn">{y}년은 이 해 숫자로 고배당기업을 골랐기 때문에, 다른 해와 바로 비교하면 안 돼요.</p>}
      <div className="g3-grid" role="table" aria-label={`${y}년 배당성향과 배당 증가율로 나눈 회사 수`}>
        <div />
        {GRID_COLS.map(([a, b]) => <div key={a} className="g3-h" role="columnheader">{a}<br />{b}</div>)}
        {g.map((row, i) => [
          <div key={`r${i}`} className="g3-r" role="rowheader">{GRID_ROWS[i]}</div>,
          ...row.map((v, j) => {
            const pct = (v / Math.max(1, tot)) * 100, ok = GRID_OK.some(([r, c]) => r === i && c === j)
            return (
              <div key={`${i}-${j}`} role="cell" className={`g3-c${ok ? ' ok' : ''}`} style={{ background: `rgba(61,107,255,${(0.05 + 0.45 * v / mx).toFixed(2)})` }}>
                {ok && <span className="g3-tag">충족</span>}
                <div className="g3-n">{v.toLocaleString('ko-KR')}곳</div>
                <div className="g3-p">{pct.toFixed(1)}%</div>
                <div className="g3-bt"><div style={{ width: `${pct.toFixed(1)}%` }} /></div>
              </div>
            )
          }),
        ])}
      </div>
      <div className="g3-legend">
        <span><i className="g3-sw ok" />요건을 채우는 칸</span>
        <span><i className="g3-sw" />색이 진할수록 회사가 많음</span>
        <span>연도 아래 %는 요건 칸 비율</span>
      </div>
    </div>
  )
}
