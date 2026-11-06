// 금융 상식 칼럼의 그림 도구. 초등학생도 손으로 움직여 보며 알 수 있게 만든 장난감 같은 그림이다.
// 여기 숫자는 읽는 사람이 고르는 예시이고 실제 회사 숫자가 아니다(세율 계단만 /api/tax/separate로 실제 계산).
import { useEffect, useState } from 'react'
import { api } from '../api'
import { useLoad, won } from '../util'

function Slider({ label, value, min, max, step = 1, unit, onChange }: { label: string; value: number; min: number; max: number; step?: number; unit: string; onChange: (v: number) => void }) {
  return (
    <label className="toy-slider">
      <span>{label} <b className="num">{value.toLocaleString('ko-KR')}{unit}</b></span>
      <input type="range" min={min} max={max} step={step} value={value} onChange={e => onChange(Number(e.target.value))} />
    </label>
  )
}

const Toy = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <div className="card toy"><span className="col-no">직접 해 보기 · {title}</span>{children}</div>
)

/** 피자 나눠 먹기: 순이익 피자에서 배당으로 나눠 주는 조각 */
export function Pizza() {
  const [slices, setSlices] = useState(3) // 10조각 중 나눠 줄 조각
  const total = 10, R = 90, C = 110
  const pct = slices / total * 100
  const arc = (i: number) => {
    const a0 = (i / total) * 2 * Math.PI - Math.PI / 2, a1 = ((i + 1) / total) * 2 * Math.PI - Math.PI / 2
    return `M${C},${C} L${C + R * Math.cos(a0)},${C + R * Math.sin(a0)} A${R},${R} 0 0 1 ${C + R * Math.cos(a1)},${C + R * Math.sin(a1)} Z`
  }
  return (
    <Toy title="피자 나눠 먹기">
      <div className="toy-row">
        <svg viewBox="0 0 220 220" className="toy-pizza" role="img" aria-label={`피자 10조각 중 ${slices}조각을 나눠 줌`}>
          <circle cx={C} cy={C} r={R + 8} fill="#E8B26A" />
          {Array.from({ length: total }, (_, i) => (
            <path key={i} d={arc(i)} fill={i < slices ? '#FFC93C' : '#FBE3B4'} stroke="#E8B26A" strokeWidth={2}
              style={{ transform: i < slices ? 'scale(1.04)' : 'none', transformOrigin: `${C}px ${C}px`, transition: 'all .3s' }} />
          ))}
          {Array.from({ length: total }, (_, i) => {
            const a = ((i + .5) / total) * 2 * Math.PI - Math.PI / 2
            return <circle key={i} cx={C + 55 * Math.cos(a)} cy={C + 55 * Math.sin(a)} r={7} fill={i < slices ? '#F2555A' : '#E9A8A0'} />
          })}
        </svg>
        <div style={{ flex: 1 }}>
          <p className="toy-big">피자 한 판 = 회사가 1년 동안 남긴 돈(순이익)</p>
          <Slider label="주주에게 나눠 줄 조각" value={slices} min={0} max={10} unit="조각" onChange={setSlices} />
          <p className="toy-result">배당성향 <b>{pct}%</b></p>
          <div className="chips">
            <span className={`badge ${pct >= 25 ? 'badge--ok' : 'badge--hold'}`}>25% 이상 {pct >= 25 ? '✓' : '✕'}</span>
            <span className={`badge ${pct >= 40 ? 'badge--ok' : 'badge--hold'}`}>40% 이상 {pct >= 40 ? '✓' : '✕'}</span>
          </div>
          <p className="small" style={{ marginTop: 8 }}>남은 {total - slices}조각은 회사가 다음 장사에 쓰려고 남겨 둬요.</p>
        </div>
      </div>
    </Toy>
  )
}

const PRESETS = [5_000_000, 20_000_000, 50_000_000, 300_000_000, 1_000_000_000]

/** 세율 계단: 특례배당소득을 넣으면 계단마다 세액이 쌓인다 (계산은 /api/tax/separate) */
export function TaxStairs() {
  const [amount, setAmount] = useState(30_000_000)
  const [r, setR] = useState<Awaited<ReturnType<typeof api.separate>> | null>(null)
  useEffect(() => {
    const t = setTimeout(() => api.separate(amount).then(setR).catch(() => setR(null)), 150)
    return () => clearTimeout(t)
  }, [amount])
  const maxTax = r ? Math.max(...r.steps.map(s => s.tax), 1) : 1
  return (
    <Toy title="세율 계단">
      <label className="toy-big" htmlFor="sep-amount" style={{ display: 'block' }}>고배당기업에서 받은 배당이 <b className="num">{won(amount)}</b>이면?</label>
      <input id="sep-amount" type="range" min={0} max={3} step={0.01} style={{ width: '100%' }}
        value={Math.log10(Math.max(amount, 1_000_000) / 1_000_000)} aria-valuetext={won(amount)}
        onChange={e => setAmount(Math.round(10 ** Number(e.target.value) * 1_000_000 / 100_000) * 100_000)} />
      <div className="chips" style={{ margin: '6px 0 16px' }}>{PRESETS.map(p => <button key={p} className="chip" onClick={() => setAmount(p)}>{won(p)}</button>)}</div>
      {r && (
        <>
          <div className="stair-row">
            {r.steps.map(s => (
              <div key={s.from} className={`stair ${s.part > 0 ? 'on' : ''}`} style={{ minHeight: 70 + s.rate_pct * 6 }}>
                <b>{s.rate_pct}%</b>
                <span>{s.to ? `${won(s.from)} 초과 ~ ${won(s.to)}` : `${won(s.from)} 초과`}</span>
                {s.part > 0 && <em className="num">{won(s.part)} × {s.rate_pct}%<br />= {won(s.tax)}</em>}
                <i style={{ height: `${s.tax / maxTax * 100}%` }} />
              </div>
            ))}
          </div>
          <div className="taxbig" style={{ marginTop: 16 }}>
            <span className="small" style={{ fontWeight: 800 }}>분리과세 세액 (참고용 계산)</span><br />
            <b className="num">{won(r.tax)}</b> <span className="small">· 받은 배당의 {r.effective_pct}%</span>
          </div>
          <p className="small" style={{ margin: 0 }}>지방소득세는 넣지 않았어요. 세율 출처: {r.source}. {r.notice}</p>
        </>
      )}
    </Toy>
  )
}

const GATES = [
  { no: '제1호', title: '상장회사일 것', text: '사업연도가 끝날 때 증권시장에 이름이 올라 있어야 해요(코넥스 제외).' },
  { no: '제2호', title: '배당이 줄지 않을 것', text: '직전 사업연도 배당소득이 2024년이 속한 사업연도보다 줄지 않아야 해요.' },
  { no: '제3호', title: '가목 또는 나목', text: '가목: 배당성향 40% 이상 / 나목: 25% 이상이면서 배당을 10% 이상 늘림' },
]

/** 문 세 개: 체크하면 문이 열리고, 셋 다 열려야 통과 */
export function Gates() {
  const [open, setOpen] = useState([true, false, true])
  const pass = open.every(Boolean)
  return (
    <Toy title="문 세 개 열어 보기">
      <p className="small" style={{ marginTop: 0 }}>문을 눌러 열고 닫아 보세요. 셋 다 열려야 고배당기업이에요.</p>
      <div className="gates">
        {GATES.map((g, i) => (
          <button key={g.no} className={`gate ${open[i] ? 'open' : ''}`} aria-pressed={open[i]} onClick={() => setOpen(o => o.map((v, k) => (k === i ? !v : v)))}>
            <span className="gate-arch" aria-hidden="true">{open[i] ? '✓' : '✕'}</span>
            <span className="col-no">{g.no}</span>
            <h4>{g.title}</h4>
            <p>{g.text}</p>
            {i < 2 && <span className="gate-and" aria-hidden="true">그리고</span>}
          </button>
        ))}
      </div>
      <p className="toy-result" aria-live="polite">{pass ? '🎉 세 문 모두 통과! 고배당기업이에요' : `✕ ${open.map((v, i) => (v ? '' : GATES[i].no)).filter(Boolean).join(', ')}에서 막혔어요`}</p>
    </Toy>
  )
}

/** 저울: 부채가 자본의 2배를 넘는지 */
export function Balance() {
  const [debt, setDebt] = useState(150)
  const [equity, setEquity] = useState(100)
  const ratio = debt / Math.max(equity, 1)
  const tilt = Math.max(-14, Math.min(14, (debt - equity * 2) / 10))
  const over = debt > equity * 2
  return (
    <Toy title="빚 저울">
      <svg viewBox="0 0 400 190" className="toy-svg" role="img" aria-label={`부채 ${debt}억, 자본 ${equity}억`}>
        <polygon points="190,180 210,180 200,110" fill="#C5CCD6" />
        <g style={{ transform: `rotate(${tilt}deg)`, transformOrigin: '200px 110px', transition: 'transform .4s' }}>
          <rect x={40} y={106} width={320} height={8} rx={4} fill="#6B7684" />
          <rect x={40} y={106 - Math.min(80, debt / 4)} width={90} height={Math.min(80, debt / 4)} rx={8} fill="#F2555A" opacity={.85} />
          <text x={85} y={100 - Math.min(80, debt / 4)} textAnchor="middle" fontSize={14} fontWeight={800} fill="#F2555A">빚(부채)</text>
          <rect x={270} y={106 - Math.min(80, equity * 2 / 4)} width={90} height={Math.min(80, equity * 2 / 4)} rx={8} fill="#3D6BFF" opacity={.85} />
          <text x={315} y={100 - Math.min(80, equity * 2 / 4)} textAnchor="middle" fontSize={14} fontWeight={800} fill="#2547D9">자기 돈 × 2</text>
        </g>
      </svg>
      <Slider label="빌린 돈(부채)" value={debt} min={0} max={320} step={10} unit="억" onChange={setDebt} />
      <Slider label="자기 돈(자본)" value={equity} min={10} max={160} step={10} unit="억" onChange={setEquity} />
      <p className="toy-result" aria-live="polite">빚이 자기 돈의 <b>{ratio.toFixed(1)}배</b> → 적자라면 배당성향을 <b>{over ? '0%' : '25%'}</b>로 봐요</p>
    </Toy>
  )
}

/** 용돈 지갑: 들어온 돈 − 꼭 쓸 돈 = 남은 돈, 남은 돈 ÷ 줄 배당 = 재무 여력 */
export function Wallet() {
  const [cashIn, setCashIn] = useState(100)
  const [must, setMust] = useState(60)
  const [pay, setPay] = useState(20)
  const left = cashIn - must
  const cover = pay > 0 ? left / pay : 0
  const W = 360, s = (v: number) => Math.max(0, v) / 140 * W
  return (
    <Toy title="용돈 지갑">
      <svg viewBox={`0 0 ${W + 120} 150`} className="toy-svg" role="img" aria-label={`들어온 돈 ${cashIn}, 꼭 쓸 돈 ${must}, 남은 돈 ${left}`}>
        {[['들어온 돈', cashIn, '#19B36B'], ['꼭 쓸 돈', must, '#FFA26B'], ['남은 돈', left, '#3D6BFF'], ['줄 배당', pay, '#FFC93C']].map(([name, v, col], i) => (
          <g key={name as string}>
            <text x={0} y={22 + i * 34} fontSize={13} fontWeight={800} fill="#191F28">{name as string}</text>
            <rect x={90} y={8 + i * 34} width={s(v as number)} height={22} rx={11} fill={col as string} style={{ transition: 'width .3s' }} />
            <text x={96 + s(v as number)} y={24 + i * 34} fontSize={13} fontWeight={800} fill="#6B7684">{(v as number).toLocaleString('ko-KR')}억</text>
          </g>
        ))}
      </svg>
      <Slider label="장사해서 들어온 돈(영업현금흐름)" value={cashIn} min={0} max={140} step={5} unit="억" onChange={setCashIn} />
      <Slider label="공장·기계에 꼭 쓸 돈(설비투자)" value={must} min={0} max={140} step={5} unit="억" onChange={setMust} />
      <Slider label="내년에 줘야 할 배당" value={pay} min={5} max={80} step={5} unit="억" onChange={setPay} />
      <p className="toy-result" aria-live="polite">남은 돈(잉여현금흐름) <b>{left}억</b> → 배당의 <b>{cover.toFixed(1)}배</b>{cover < 1 ? ' · 남은 돈만으로는 모자라요' : ' · 남은 돈으로 줄 수 있어요'}</p>
    </Toy>
  )
}

/** 달리기 시합: 실제 '배당을 늘린다는 공시' 한 건. 60거래일 동안 그 회사 주가와 시장지수가 얼마나 달렸는지 다시 본다. */
export function Race() {
  const [pick, setPick] = useState(() => Math.floor(Math.random() * 10000))
  const [r, setR] = useState<Awaited<ReturnType<typeof api.race>> | null>(null)
  const [day, setDay] = useState(0)
  const [playing, setPlaying] = useState(false)
  useEffect(() => { api.race(pick).then(x => { setR(x); setDay(0); setPlaying(true) }).catch(() => setR(null)) }, [pick])
  useEffect(() => {
    if (!playing || !r) return
    if (day >= r.path.length - 1) { setPlaying(false); return }
    const t = setTimeout(() => setDay(d => d + 1), 70)
    return () => clearTimeout(t)
  }, [playing, day, r])
  if (!r) return <Toy title="달리기 시합"><p className="small">불러오는 중…</p></Toy>
  const W = 420, H = 220, L = 40, R = 70, T = 16, B = 190
  const all = r.path.flatMap(p => [p[1], p[2]])
  const lo = Math.min(...all, 0) - 2, hi = Math.max(...all, 0) + 2
  const X = (d: number) => L + (W - L - R) * d / 60, Y = (v: number) => B - (B - T) * (v - lo) / (hi - lo)
  const shown = r.path.slice(0, day + 1)
  const [, s, m] = shown[shown.length - 1]
  const gap = Math.round((s - m) * 100) / 100
  const band = shown.map(p => `${X(p[0])},${Y(p[1])}`).concat([...shown].reverse().map(p => `${X(p[0])},${Y(p[2])}`)).join(' ')
  const sign = (v: number) => `${v > 0 ? '+' : ''}${v.toFixed(1)}%`
  return (
    <Toy title="진짜 달리기 시합 다시 보기">
      <p className="small" style={{ marginTop: 0 }}>실제로 있었던 "배당을 늘린다는 공시" {r.n_events}건 중 하나예요({r.year}년, {r.market}). 공시한 날부터 60거래일 동안(공시 전날 값을 0%로), 이 회사 주가와 시장지수가 얼마나 올랐는지 같이 달려요. 회사 이름은 보여 주지 않아요.</p>
      <svg viewBox={`0 0 ${W} ${H + 10}`} className="toy-svg" role="img" aria-label={`${day}거래일째 회사 ${sign(s)}, 시장 ${sign(m)}`}>
        <line x1={L} x2={W - R} y1={Y(0)} y2={Y(0)} stroke="#191F28" strokeDasharray="3 4" />
        <text x={L - 6} y={Y(0) + 4} textAnchor="end" fontSize={11} fill="#6B7684">0%</text>
        {[0, 20, 40, 60].map(d => <text key={d} x={X(d)} y={H + 6} textAnchor="middle" fontSize={11} fill="#6B7684">{d}일</text>)}
        <polygon points={band} fill={gap >= 0 ? 'rgba(61,107,255,.16)' : 'rgba(242,85,90,.16)'} />
        <polyline points={shown.map(p => `${X(p[0])},${Y(p[2])}`).join(' ')} fill="none" stroke="#8B95A5" strokeWidth={3} />
        <polyline points={shown.map(p => `${X(p[0])},${Y(p[1])}`).join(' ')} fill="none" stroke="#3D6BFF" strokeWidth={3} />
        <circle cx={X(day)} cy={Y(m)} r={9} fill="#8B95A5" /><text x={X(day) + 13} y={Y(m) + 4} fontSize={12} fontWeight={800} fill="#6B7684">시장 {sign(m)}</text>
        <circle cx={X(day)} cy={Y(s)} r={9} fill="#3D6BFF" /><text x={X(day) + 13} y={Y(s) + 4} fontSize={12} fontWeight={800} fill="#2547D9">회사 {sign(s)}</text>
      </svg>
      <div className="chips">
        <button className="btn btn--soft btn--sm" onClick={() => { setDay(0); setPlaying(true) }}>▶ 처음부터 다시</button>
        <button className="btn btn--sm" onClick={() => setPick(p => p + 1 + Math.floor(Math.random() * 50))}>🎲 다른 공시 뽑기</button>
      </div>
      <p className="toy-result" aria-live="polite">{day}거래일째 · 초과수익률 = 회사 {sign(s)} − 시장 {sign(m)} = <b style={{ color: gap >= 0 ? 'var(--sea)' : 'var(--no)' }}>{gap > 0 ? '+' : ''}{gap.toFixed(1)}%p</b>
        {' '}{s >= 0 && gap < 0 ? '· 올랐지만 시장보다 뒤처졌어요' : s < 0 && gap >= 0 ? '· 내렸지만 시장보다는 덜 내렸어요' : gap >= 0 ? '· 시장보다 잘 달렸어요' : '· 시장보다 뒤처졌어요'}</p>
      <p className="small" style={{ margin: 0 }}>몇 번 뽑아 보세요. 같은 "배당을 늘린다는 공시"인데도 결과가 제각각이에요. 그래서 데이터 이야기에서는 {r.n_events}건을 모아 가운데 값으로 봐요. 이 그림은 배당을 빼고 주가만 본 값이라, 데이터 이야기의 숫자(날마다 차이를 더하고 배당을 넣은 값)와 조금 달라요.</p>
    </Toy>
  )
}

const median = (v: number[]) => { const s = [...v].sort((a, b) => a - b), n = s.length; return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2 }
const quantile = (s: number[], p: number) => { const i = (s.length - 1) * p, lo = Math.floor(i), hi = Math.ceil(i); return s[lo] + (s[hi] - s[lo]) * (i - lo) }

/** 평균과 가운데 값: 실제 '배당을 늘린다는 공시' 사례 전부를 점으로 찍고, 크게 오른·내린 사례를 빼 본다 */
export function Spread() {
  const all = useLoad(api.spread).data
  const [cut, setCut] = useState<'none' | 'top' | 'bottom'>('none')
  if (!all) return <Toy title="점 찍어 보기"><p className="small">불러오는 중…</p></Toy>
  const K = 20
  const v = cut === 'top' ? all.values.slice(0, -K) : cut === 'bottom' ? all.values.slice(K) : all.values
  const mean = v.reduce((a, b) => a + b, 0) / v.length, mid = median(v), q1 = quantile(v, .25), q3 = quantile(v, .75)
  const LO = -40, HI = 80, BIN = 2, W = 440, L = 22, R = 22, B = 200, DOT = 5.2
  const X = (x: number) => L + (W - L - R) * (Math.max(LO, Math.min(HI, x)) - LO) / (HI - LO)
  const stacks = new Map<number, number>()
  const dots = all.values.map(x => {
    const b = Math.floor((Math.max(LO, Math.min(HI - .01, x)) - LO) / BIN)
    const k = stacks.get(b) ?? 0
    stacks.set(b, k + 1)
    return { x, cx: L + (b + .5) * (W - L - R) / ((HI - LO) / BIN), cy: B - 4 - k * DOT, out: !v.includes(x) }
  })
  const top = Math.min(...dots.map(d => d.cy)) - 10
  const sign = (n: number) => `${n > 0 ? '+' : ''}${n.toFixed(2)}%p`
  return (
    <Toy title="점 찍어 보기">
      <p className="small" style={{ marginTop: 0 }}>점 하나가 실제 "배당을 늘린다는 공시" 한 건이에요. 공시 뒤 60거래일 동안 시장보다 얼마나 더 올랐는지(초과수익률)에 따라 줄을 세웠어요. 모두 {all.values.length}건이에요.</p>
      <div className="spread-legend">
        <span><i className="lg-mean" />평균 <b>{sign(mean)}</b></span>
        <span><i className="lg-mid" />가운데 값 <b>{sign(mid)}</b></span>
        <span><i className="lg-iqr" />가운데 절반 {q1.toFixed(1)}~{q3.toFixed(1)}%p</span>
      </div>
      <svg viewBox={`${0} ${top} ${W} ${B - top + 26}`} className="toy-svg" role="img" aria-label={`평균 ${sign(mean)}, 가운데 값 ${sign(mid)}`}>
        <rect x={X(q1)} y={top} width={X(q3) - X(q1)} height={B - top} fill="rgba(61,107,255,.08)" />
        {dots.map((d, i) => <circle key={i} cx={d.cx} cy={d.cy} r={DOT / 2 - .3} fill={d.out ? '#E5E8EE' : d.x >= 0 ? '#3D6BFF' : '#F2555A'} opacity={d.out ? 1 : .75} style={{ transition: 'fill .3s' }} />)}
        <line x1={X(0)} x2={X(0)} y1={top} y2={B} stroke="#191F28" strokeWidth={1} strokeDasharray="2 3" />
        <line x1={X(mean)} x2={X(mean)} y1={top} y2={B} stroke="#F2555A" strokeWidth={3} strokeDasharray="6 4" style={{ transition: 'all .4s' }} />
        <line x1={X(mid)} x2={X(mid)} y1={top} y2={B} stroke="#2547D9" strokeWidth={3} style={{ transition: 'all .4s' }} />
        <line x1={L} x2={W - R} y1={B} y2={B} stroke="#191F28" />
        {[-40, -20, 0, 20, 40, 60, 80].map(t => <text key={t} x={X(t)} y={B + 16} textAnchor="middle" fontSize={11} fill="#6B7684">{t > 0 ? '+' : ''}{t}%p</text>)}
      </svg>
      <div className="chips">
        <button className="chip" aria-pressed={cut === 'none'} onClick={() => setCut('none')} style={cut === 'none' ? { background: 'var(--sea)', color: '#fff' } : undefined}>모두 보기</button>
        <button className="chip" aria-pressed={cut === 'top'} onClick={() => setCut('top')} style={cut === 'top' ? { background: 'var(--sea)', color: '#fff' } : undefined}>가장 많이 오른 {K}건 빼 보기</button>
        <button className="chip" aria-pressed={cut === 'bottom'} onClick={() => setCut('bottom')} style={cut === 'bottom' ? { background: 'var(--sea)', color: '#fff' } : undefined}>가장 많이 내린 {K}건 빼 보기</button>
      </div>
      <p className="toy-result" aria-live="polite">
        {cut === 'none' ? '몇 건만 아주 크게 올라서, 평균이 가운데 값보다 오른쪽으로 끌려가 있어요.'
          : `${K}건만 뺐는데 평균은 ${sign(mean)}로 크게 움직이고, 가운데 값은 ${sign(mid)}로 조금만 움직여요.`}
      </p>
      <p className="small" style={{ margin: 0 }}>{all.basis}. −40%p보다 낮거나 +80%p보다 높은 점은 양 끝에 모았어요. 데이터 이야기 6장의 가운데 값과 같은 사례예요.</p>
    </Toy>
  )
}

/** 동전 던지기: 우연히 한쪽으로 쏠리는 정도 */
export function Coins() {
  const [n, setN] = useState(10)
  const [flips, setFlips] = useState<boolean[]>([])
  const heads = flips.filter(Boolean).length
  const throwAll = () => setFlips(Array.from({ length: n }, () => Math.random() < .5))
  // 공정한 동전에서 앞면이 이만큼 이상 치우칠 확률(양쪽): 이항분포로 직접 계산
  const pTwoSided = (() => {
    if (!flips.length) return null
    const k = Math.abs(heads - n / 2)
    let p = 0, c = 1
    for (let i = 0; i <= n; i++) { if (Math.abs(i - n / 2) >= k) p += c; c = c * (n - i) / (i + 1) }
    return Math.min(1, p / 2 ** n)
  })()
  return (
    <Toy title="동전 던지기">
      <div className="chips" style={{ marginBottom: 12 }}>
        {[10, 100].map(k => <button key={k} className="chip" aria-pressed={n === k} onClick={() => { setN(k); setFlips([]) }} style={n === k ? { background: 'var(--sea)', color: '#fff' } : undefined}>{k}번 던지기</button>)}
        <button className="btn btn--sm" onClick={throwAll}>🪙 던지기</button>
      </div>
      <div className="coins" aria-hidden="true">
        {flips.map((h, i) => <span key={`${flips.length}-${i}`} className={`coin ${h ? 'h' : 't'}`} style={{ animationDelay: `${Math.min(i, 40) * 15}ms` }}>{n <= 10 ? (h ? '앞' : '뒤') : ''}</span>)}
      </div>
      {pTwoSided != null && (
        <p className="toy-result" aria-live="polite">앞면 <b>{heads}</b> / {n}번 ({Math.round(heads / n * 100)}%) · 보통 동전으로 이만큼 치우칠 가능성(p값) <b>{pTwoSided < 0.0001 ? '0.0001보다 작음' : pTwoSided.toFixed(3)}</b>
          {' '}→ {pTwoSided < 0.05 ? '우연이라 보기 어려워요' : '우연일 수도 있어요'}</p>
      )}
      <p className="small" style={{ margin: 0 }}>여러 번 던져 보세요. 10번일 때는 7:3도 자주 나오지만, 100번이면 대부분 절반 근처에 모여요.</p>
    </Toy>
  )
}

/** 주식과 채권: 가게 장사가 잘되든 안되든 채권자는 정해진 이자, 주주는 남는 만큼 */
export function StockBond() {
  const [profit, setProfit] = useState(60) // 이자 내기 전 가게가 번 돈(억)
  const interest = 10 // 빌린 돈 100억에 이자 10%
  const left = profit - interest
  const W = 420, mid = 210, sc = (v: number) => Math.min(150, Math.abs(v)) * 1.2
  return (
    <Toy title="가게 주인과 돈 빌려준 사람">
      <p className="small" style={{ marginTop: 0 }}>가게를 열려고 주인들이 돈을 내고(주식), 은행 같은 곳에서 100억 원을 빌렸어요(채권, 이자 10%). 올해 장사를 얼마나 잘했는지 움직여 보세요.</p>
      <Slider label="올해 가게가 번 돈(이자 내기 전)" value={profit} min={-40} max={120} step={5} unit="억" onChange={setProfit} />
      <svg viewBox={`0 0 ${W} 150`} className="toy-svg" role="img" aria-label={`채권자 ${interest}억, 주주 몫 ${left}억`}>
        <line x1={mid} x2={mid} y1={10} y2={140} stroke="#191F28" strokeDasharray="3 4" />
        <text x={mid} y={148} textAnchor="middle" fontSize={11} fill="#6B7684">0원</text>
        <text x={8} y={44} fontSize={13} fontWeight={800} fill="#191F28">채권자(빌려준 사람)</text>
        <rect x={mid} y={52} width={sc(interest)} height={22} rx={11} fill="#8B95A5" />
        <text x={mid + sc(interest) + 6} y={68} fontSize={13} fontWeight={800} fill="#6B7684">이자 {interest}억 (늘 같아요)</text>
        <text x={8} y={102} fontSize={13} fontWeight={800} fill="#191F28">주주(가게 주인)</text>
        <rect x={left >= 0 ? mid : mid - sc(left)} y={110} width={sc(left)} height={22} rx={11} fill={left >= 0 ? '#3D6BFF' : '#F2555A'} style={{ transition: 'all .3s' }} />
        <text x={left >= 0 ? mid + sc(left) + 6 : mid - sc(left) - 6} y={126} textAnchor={left >= 0 ? 'start' : 'end'} fontSize={13} fontWeight={800} fill={left >= 0 ? '#2547D9' : '#F2555A'}>{left >= 0 ? `남는 몫 ${left}억` : `손해 ${-left}억`}</text>
      </svg>
      <p className="toy-result" aria-live="polite">{left > 30 ? '장사가 잘되면 주주 몫이 커져요. 채권자 이자는 그대로예요.' : left >= 0 ? '이자를 먼저 주고 남은 만큼이 주주 몫이에요.' : '장사가 안돼도 이자는 줘야 해요. 손해는 주주가 먼저 떠안아요.'}</p>
      <p className="small" style={{ margin: 0 }}>그래서 주식은 많이 벌 수도, 잃을 수도 있고(위험이 커요), 채권은 받을 돈이 정해져 있어요(회사가 망하지 않는 한). 예시 숫자예요.</p>
    </Toy>
  )
}

/** 의결권과 배당권: 가진 주식 수만큼 표를 던지고, 그만큼 배당을 받는다 */
export function Votes() {
  const [mine, setMine] = useState(10) // 전체 100주 중 내 주식
  const [total, setTotal] = useState(50) // 회사가 주주들에게 줄 배당 총액(만 원)
  const share = mine / 100
  const cells = Array.from({ length: 100 }, (_, i) => i < mine)
  return (
    <Toy title="주식 100주짜리 회사">
      <div className="toy-row">
        <div className="vote-grid" aria-hidden="true">{cells.map((m, i) => <span key={i} className={m ? 'me' : ''} />)}</div>
        <div>
          <Slider label="내가 가진 주식" value={mine} min={1} max={60} unit="주" onChange={setMine} />
          <Slider label="회사가 나눠 줄 배당 총액" value={total} min={0} max={200} step={10} unit="만 원" onChange={setTotal} />
          <p className="toy-result" aria-live="polite">의결권 <b>{mine}표</b> / 100표 ({Math.round(share * 100)}%)<br />배당권 <b>{(total * share).toLocaleString('ko-KR', { maximumFractionDigits: 1 })}만 원</b></p>
          <p className="small" style={{ margin: 0 }}>{mine > 50 ? '절반이 넘으니 주주총회에서 혼자 결정할 수 있어요.' : '절반이 안 되면 다른 주주들과 뜻을 모아야 해요.'}</p>
        </div>
      </div>
    </Toy>
  )
}

const HELPERS = [
  { who: '나', icon: '🙋', does: '배당을 받고, 보유 종목과 소득을 알아요.', not: '' },
  { who: '원픽 점검', icon: '🦦', does: '내 종목이 대상인지, 신청하면 세금이 얼마나 달라지는지 계산하고 근거를 보여 줘요.', not: '세금을 줄이는 방법을 정해 주거나 신청을 권하지 않아요.' },
  { who: '세무사', icon: '🧑‍💼', does: '내 소득 전체를 보고 신청할지 함께 판단하고, 종합소득세 신고를 대신해 줘요(신고 대리·세무 상담).', not: '' },
  { who: '세무서', icon: '🏛️', does: '5월 종합소득세 확정신고와 분리과세신청서를 받아요.', not: '' },
]

/** 세무사는 어떻게 도와줄까: 누가 무엇을 하는지 차례대로 */
export function TaxHelper() {
  const [on, setOn] = useState(1)
  return (
    <Toy title="누가 무엇을 해요?">
      <div className="helper-row" role="tablist">
        {HELPERS.map((h, i) => (
          <button key={h.who} role="tab" aria-selected={on === i} className={`helper ${on === i ? 'on' : ''}`} onClick={() => setOn(i)}>
            <span className="helper-icon" aria-hidden="true">{h.icon}</span>{h.who}
            {i < HELPERS.length - 1 && <span className="helper-arrow" aria-hidden="true">→</span>}
          </button>
        ))}
      </div>
      <div className="helper-card" aria-live="polite">
        <b>{HELPERS[on].who}</b>가 하는 일: {HELPERS[on].does}
        {HELPERS[on].not && <p className="small" style={{ margin: '6px 0 0' }}>하지 않는 일: {HELPERS[on].not}</p>}
      </div>
    </Toy>
  )
}

const TIMELINE = [
  { m: '3~4월', what: '봄 배당이 들어와요', asis: '', tobe: '' },
  { m: '4~5월', what: '내 배당, 분리과세 대상일까?', asis: '스스로 공시를 찾아봐야 해요', tobe: '원픽 점검으로 미리 계산해요' },
  { m: '5월', what: '종합소득세 확정신고', asis: '신고 때가 돼서야 세금을 알아요', tobe: '세무사 상담·신고대행으로 이어져요' },
  { m: '다음 해 2~3월', what: '회사의 다음 배당 결정 공시', asis: '내년에도 대상인지 몰라요', tobe: '회사가 얼마를 배당해야 하는지 미리 알아요' },
]

/** 자산관리서비스: 1년 동안 언제 무엇을 도와주는지 */
export function WealthMap() {
  const [tobe, setTobe] = useState(true)
  return (
    <Toy title="배당을 받는 1년">
      <div className="chips" style={{ marginBottom: 12 }}>
        <button className="chip" aria-pressed={!tobe} onClick={() => setTobe(false)} style={!tobe ? { background: 'var(--hold)', color: '#fff' } : undefined}>지금까지</button>
        <button className="chip" aria-pressed={tobe} onClick={() => setTobe(true)} style={tobe ? { background: 'var(--sea)', color: '#fff' } : undefined}>원픽을 더하면</button>
      </div>
      <ol className="timeline">
        {TIMELINE.map(t => (
          <li key={t.m}>
            <span className="tl-m">{t.m}</span>
            <b>{t.what}</b>
            {(tobe ? t.tobe : t.asis) && <span className={`tl-note ${tobe ? 'tobe' : 'asis'}`}>{tobe ? t.tobe : t.asis}</span>}
          </li>
        ))}
      </ol>
    </Toy>
  )
}

const pctTxt = (v: number, d = 1) => `${v.toLocaleString('ko-KR', { maximumFractionDigits: d })}%`
const manwon = (v: number) => `${v.toLocaleString('ko-KR')}만 원`

/** 금융소득 2천만 원 선: 이자 + 배당을 쌓아 선을 넘는지 */
export function FinIncome() {
  const [interest, setInterest] = useState(800)
  const [dividend, setDividend] = useState(1500)
  const total = interest + dividend, LINE = 2000, MAX = 5000, W = 420
  const x = (v: number) => Math.min(v, MAX) / MAX * W
  return (
    <Toy title="2천만 원 선 넘겨 보기">
      <svg viewBox={`0 0 ${W} 90`} className="toy-svg" role="img" aria-label={`금융소득 ${total}만 원`}>
        <rect x={0} y={28} width={x(interest)} height={34} rx={8} fill="#8B95A5" style={{ transition: 'width .3s' }} />
        <rect x={x(interest)} y={28} width={x(total) - x(interest)} height={34} rx={8} fill="#3D6BFF" style={{ transition: 'all .3s' }} />
        <line x1={x(LINE)} x2={x(LINE)} y1={10} y2={80} stroke="#F2555A" strokeWidth={3} />
        <text x={x(LINE) + 6} y={20} fontSize={12} fontWeight={800} fill="#F2555A">2천만 원</text>
        <text x={4} y={78} fontSize={12} fontWeight={700} fill="#6B7684">이자 {manwon(interest)} + 배당 {manwon(dividend)}</text>
      </svg>
      <Slider label="1년 예금·채권 이자" value={interest} min={0} max={3000} step={100} unit="만 원" onChange={setInterest} />
      <Slider label="1년 배당" value={dividend} min={0} max={3000} step={100} unit="만 원" onChange={setDividend} />
      <p className="toy-result" aria-live="polite">금융소득 <b>{manwon(total)}</b> → {total > LINE ? `2천만 원을 ${manwon(total - LINE)} 넘었어요. 다른 소득과 합쳐 다시 계산해요(종합과세).` : '2천만 원 이하라 미리 뗀 세금으로 끝나요.'}</p>
    </Toy>
  )
}

/** 원천징수: 배당 받는 날 통장 */
export function Withhold() {
  const [amount, setAmount] = useState(100)
  const tax = amount * 0.14, local = amount * 0.014, net = amount - tax - local
  return (
    <Toy title="배당 받는 날 통장 보기">
      <Slider label="회사가 준 배당" value={amount} min={10} max={1000} step={10} unit="만 원" onChange={setAmount} />
      <div className="receipt">
        <div><span>배당금</span><b>{amount.toLocaleString('ko-KR')}만 원</b></div>
        <div className="minus"><span>소득세 14%</span><b>− {tax.toLocaleString('ko-KR', { maximumFractionDigits: 1 })}만 원</b></div>
        <div className="minus"><span>지방소득세 1.4%</span><b>− {local.toLocaleString('ko-KR', { maximumFractionDigits: 2 })}만 원</b></div>
        <div className="sum"><span>통장에 들어온 돈</span><b>{net.toLocaleString('ko-KR', { maximumFractionDigits: 2 })}만 원</b></div>
      </div>
      <p className="small" style={{ margin: 0 }}>떼어 간 세금은 회사(증권사)가 대신 나라에 내요. 이자도 같은 비율로 떼요.</p>
    </Toy>
  )
}

const INCOME_ITEMS: [string, string][] = [
  ['회사 월급', '근로소득'], ['예금 이자', '이자소득'], ['주식 배당', '배당소득'], ['가게 수입', '사업소득'],
  ['국민연금', '연금소득'], ['강연료·원고료', '기타소득'], ['프리랜서 디자인비', '사업소득'], ['채권 이자', '이자소득'],
]
const POCKETS = ['이자소득', '배당소득', '사업소득', '근로소득', '연금소득', '기타소득']

/** 소득 주머니 나누기 */
export function IncomeSort() {
  const [pick, setPick] = useState<number | null>(null)
  const target = pick != null ? INCOME_ITEMS[pick][1] : null
  return (
    <Toy title="소득 주머니 나누기">
      <p className="small" style={{ marginTop: 0 }}>위의 돈을 눌러 보세요. 어느 주머니에 들어가는지 보여 줘요.</p>
      <div className="chips" style={{ marginBottom: 14 }}>
        {INCOME_ITEMS.map(([name], i) => <button key={name} className="chip" aria-pressed={pick === i} onClick={() => setPick(i)} style={pick === i ? { background: 'var(--ink)', color: '#fff' } : undefined}>{name}</button>)}
      </div>
      <div className="pockets">
        {POCKETS.map(pk => (
          <div key={pk} className={`pocket-box ${target === pk ? 'on' : ''} ${pk === '이자소득' || pk === '배당소득' ? 'fin' : ''}`}>
            <b>{pk}</b>{target === pk && <span className="pocket-in">{INCOME_ITEMS[pick!][0]}</span>}
          </div>
        ))}
      </div>
      <p className="small" style={{ margin: '10px 0 0' }}>파란 테두리 두 주머니(이자·배당)를 합친 것이 금융소득이에요. 여섯 주머니를 모두 합치면 종합소득이에요.</p>
    </Toy>
  )
}

/** 배당가산: 법인세 낸 이익으로 준 배당을 원래 크기로 돌려 세금 계산 후 빼 주기 (예시, 가산율 10%) */
export function GrossUp() {
  const [div, setDiv] = useState(1000)
  const up = div * 0.1
  return (
    <Toy title="두 번 내지 않게 맞추기">
      <Slider label="2천만 원 넘는 부분 중 국내 회사 배당" value={div} min={100} max={5000} step={100} unit="만 원" onChange={setDiv} />
      <div className="steps-row">
        <div><span>받은 배당</span><b>{manwon(div)}</b></div><i>+</i>
        <div className="hl"><span>배당가산 10%</span><b>{manwon(up)}</b></div><i>=</i>
        <div><span>세금 계산에 넣는 돈</span><b>{manwon(div + up)}</b></div>
      </div>
      <p className="toy-result" aria-live="polite">계산이 끝난 세금에서 더한 만큼({manwon(up)}, 배당세액공제)을 다시 빼 줘요. 회사가 이미 낸 법인세를 주주 몫에서 인정해 주는 거예요.</p>
      <p className="small" style={{ margin: 0 }}>예시 계산이에요. 실제로는 빼 주는 금액에 한도가 있고, 원픽 점검이 정확히 계산해요.</p>
    </Toy>
  )
}

/** 복리 저금통 */
export function Savings() {
  const [rate, setRate] = useState(3)
  const [years, setYears] = useState(10)
  const base = 100
  const vals = Array.from({ length: years + 1 }, (_, y) => base * (1 + rate / 100) ** y)
  const simple = base * (1 + rate / 100 * years)
  const max = Math.max(...vals, 1), W = 420, H = 150, bw = W / vals.length
  return (
    <Toy title="복리 저금통">
      <svg viewBox={`0 0 ${W} ${H + 18}`} className="toy-svg" role="img" aria-label={`${years}년 뒤 ${vals[years].toFixed(0)}만 원`}>
        {vals.map((v, y) => {
          const h = v / max * H, interest = (v - base) / max * H
          return (
            <g key={y}>
              <rect x={y * bw + 2} y={H - h} width={bw - 4} height={h - interest} rx={3} fill="#C9D6FF" />
              <rect x={y * bw + 2} y={H - h} width={bw - 4} height={interest} rx={3} fill="#FFC93C" />
              {(y === 0 || y === years || y % 5 === 0) && <text x={y * bw + bw / 2} y={H + 14} textAnchor="middle" fontSize={10} fill="#6B7684">{y}년</text>}
            </g>
          )
        })}
      </svg>
      <Slider label="금리(1년)" value={rate} min={0} max={10} step={0.5} unit="%" onChange={setRate} />
      <Slider label="맡겨 두는 기간" value={years} min={1} max={30} unit="년" onChange={setYears} />
      <p className="toy-result" aria-live="polite">100만 원 → <b>{vals[years].toLocaleString('ko-KR', { maximumFractionDigits: 0 })}만 원</b> (이자에 이자가 붙지 않으면 {simple.toLocaleString('ko-KR', { maximumFractionDigits: 0 })}만 원)</p>
      <p className="small" style={{ margin: 0 }}>노란 부분이 쌓인 이자예요. 세금은 빼지 않은 예시예요.</p>
    </Toy>
  )
}

/** 환율 다이얼 */
export function Fx() {
  const [rate, setRate] = useState(1300)
  const toy = 20, sale = 1_000_000
  return (
    <Toy title="환율 다이얼">
      <Slider label="1달러 =" value={rate} min={1000} max={1600} step={10} unit="원" onChange={setRate} />
      <div className="fx-cards">
        <div><span>🧸 미국 장난감 {toy}달러</span><b>{(toy * rate).toLocaleString('ko-KR')}원</b><em>사는 사람은 {rate > 1300 ? '더 내요' : rate < 1300 ? '덜 내요' : '그대로'}</em></div>
        <div><span>🚢 수출 기업이 100만 달러어치 팔면</span><b>{(sale * rate / 100_000_000).toLocaleString('ko-KR', { maximumFractionDigits: 1 })}억 원</b><em>원화로 {rate > 1300 ? '더 받아요' : rate < 1300 ? '덜 받아요' : '그대로'}</em></div>
      </div>
      <p className="small" style={{ margin: 0 }}>1,300원을 기준으로 견줬어요. 예시 숫자이고 지금 환율이 아니에요.</p>
    </Toy>
  )
}

/** 나라 가계부: 경상수지 */
export function Account() {
  const [exp, setExp] = useState(600)
  const [imp, setImp] = useState(550)
  const [service, setService] = useState(-20)
  const [primary, setPrimary] = useState(20)
  const goods = exp - imp, total = goods + service + primary
  const rows: [string, number][] = [['상품수지 (수출 − 수입)', goods], ['서비스수지', service], ['본원소득수지 (배당·이자 등)', primary], ['경상수지', total]]
  const W = 420, mid = 210, sc = (v: number) => Math.min(190, Math.abs(v) * 1.2)
  return (
    <Toy title="나라 가계부">
      <svg viewBox={`0 0 ${W} 150`} className="toy-svg" role="img" aria-label={`경상수지 ${total}억 달러`}>
        <line x1={mid} x2={mid} y1={0} y2={145} stroke="#191F28" strokeDasharray="3 4" />
        {rows.map(([name, v], i) => (
          <g key={name}>
            <rect x={v >= 0 ? mid : mid - sc(v)} y={8 + i * 34} width={sc(v)} height={20} rx={10} fill={i === 3 ? (v >= 0 ? '#3D6BFF' : '#F2555A') : v >= 0 ? '#9DB4FF' : '#FFB3B5'} style={{ transition: 'all .3s' }} />
            <text x={v >= 0 ? mid - 6 : mid + 6} y={23 + i * 34} textAnchor={v >= 0 ? 'end' : 'start'} fontSize={11} fontWeight={i === 3 ? 800 : 700} fill="#191F28">{name} {v > 0 ? '+' : ''}{v}</text>
          </g>
        ))}
      </svg>
      <Slider label="수출" value={exp} min={300} max={800} step={10} unit="억 달러" onChange={setExp} />
      <Slider label="수입" value={imp} min={300} max={800} step={10} unit="억 달러" onChange={setImp} />
      <Slider label="서비스수지(여행·운송 등)" value={service} min={-100} max={60} step={5} unit="억 달러" onChange={setService} />
      <Slider label="본원소득수지(해외 배당·이자 등)" value={primary} min={-60} max={100} step={5} unit="억 달러" onChange={setPrimary} />
      <p className="toy-result" aria-live="polite">경상수지 <b style={{ color: total >= 0 ? 'var(--sea)' : 'var(--no)' }}>{total > 0 ? '+' : ''}{total}억 달러</b> · {total >= 0 ? '흑자: 나라 밖에서 번 돈이 더 많아요' : '적자: 나라 밖으로 나간 돈이 더 많아요'}</p>
      <p className="small" style={{ margin: 0 }}>예시 숫자예요. 이전소득수지는 작아서 그림에서 뺐어요.</p>
    </Toy>
  )
}

/** 장바구니: 물가와 실질수익률 */
export function Basket() {
  const [infl, setInfl] = useState(3)
  const [years, setYears] = useState(10)
  const [interest, setInterest] = useState(2)
  const price = 1000 * (1 + infl / 100) ** years // 사과 한 개 값(원)
  const apples = Math.floor(10000 / price)
  const real = ((1 + interest / 100) / (1 + infl / 100) - 1) * 100
  return (
    <Toy title="장바구니">
      <div className="apples" aria-hidden="true">{Array.from({ length: 10 }, (_, i) => <span key={i} className={i < apples ? '' : 'gone'}>🍎</span>)}</div>
      <Slider label="물가 상승률(1년)" value={infl} min={0} max={10} step={0.5} unit="%" onChange={setInfl} />
      <Slider label="지난 시간" value={years} min={0} max={30} unit="년" onChange={setYears} />
      <p className="toy-result" aria-live="polite">1만 원으로 사과 <b>{apples}개</b> (처음엔 10개, 사과 한 개 {price.toLocaleString('ko-KR', { maximumFractionDigits: 0 })}원)</p>
      <Slider label="예금 이자(1년)" value={interest} min={0} max={10} step={0.5} unit="%" onChange={setInterest} />
      <p className="toy-result" aria-live="polite">실질수익률 <b style={{ color: real >= 0 ? 'var(--sea)' : 'var(--no)' }}>{real > 0 ? '+' : ''}{real.toFixed(2)}%</b> {real < 0 ? '· 통장 숫자는 늘어도 살 수 있는 물건은 줄어요' : '· 물가보다 빨리 불어나요'}</p>
    </Toy>
  )
}

/** 배당수익률 vs 배당성향 */
export function Yields() {
  const [price, setPrice] = useState(50000)
  const [dps, setDps] = useState(2000)
  const [eps, setEps] = useState(5000)
  return (
    <Toy title="배당수익률 vs 배당성향">
      <Slider label="주가" value={price} min={10000} max={100000} step={1000} unit="원" onChange={setPrice} />
      <Slider label="주당배당금" value={dps} min={0} max={6000} step={100} unit="원" onChange={setDps} />
      <Slider label="주당순이익(1주가 번 돈)" value={eps} min={500} max={10000} step={100} unit="원" onChange={setEps} />
      <div className="fx-cards">
        <div><span>배당수익률 = 주당배당금 ÷ 주가</span><b>{pctTxt(dps / price * 100, 2)}</b><em>주가가 오르면 낮아져요</em></div>
        <div><span>배당성향 = 주당배당금 ÷ 주당순이익</span><b>{pctTxt(dps / eps * 100)}</b><em>{dps / eps >= 0.4 ? '40% 이상' : dps / eps >= 0.25 ? '25~40%' : '25% 미만'}</em></div>
      </div>
      <p className="small" style={{ margin: 0 }}>주가를 움직여 보세요. 배당수익률만 바뀌고, 1주에 받는 배당금({dps.toLocaleString('ko-KR')}원)과 배당성향은 그대로예요.</p>
    </Toy>
  )
}

const MONTHS = ['1월', '2월', '3월', '4월', '5월', '6월', '7월', '8월', '9월', '10월', '11월', '12월']

/** 배당 달력: 결산·중간·분기 기준일 */
export function DivCalendar() {
  const [kind, setKind] = useState<'결산' | '중간' | '분기'>('결산')
  const marks: Record<string, number[]> = { '결산': [11], '중간': [5, 11], '분기': [2, 5, 8, 11] }
  const on = marks[kind]
  return (
    <Toy title="배당 달력">
      <div className="chips" style={{ marginBottom: 12 }}>
        {(['결산', '중간', '분기'] as const).map(k => <button key={k} className="chip" aria-pressed={kind === k} onClick={() => setKind(k)} style={kind === k ? { background: 'var(--sea)', color: '#fff' } : undefined}>{k}배당까지 주는 회사</button>)}
      </div>
      <div className="cal">{MONTHS.map((m, i) => <span key={m} className={on.includes(i) ? 'on' : ''}>{m}{on.includes(i) && <i>🪙</i>}</span>)}</div>
      <p className="toy-result" aria-live="polite">1년에 <b>{on.length}번</b> · {kind === '결산' ? '12월 31일 기준, 다음 해 봄에 받아요' : kind === '중간' ? '6월 말 기준 한 번 더' : '3·6·9·12월 말 기준으로 네 번'}</p>
      <p className="small" style={{ margin: 0 }}>12월 결산 회사의 흔한 예시예요. 기준일은 회사마다 달라요.</p>
    </Toy>
  )
}

const DAYS = ['월', '화', '수', '목', '금']

/** 언제 사야 받을까: 이틀 뒤 결제, 기준일 금요일 */
export function RecordDay() {
  const [buy, setBuy] = useState(1)
  const record = 4 // 금요일이 기준일
  const settle = buy + 2
  const ok = settle <= record
  return (
    <Toy title="언제 사야 받을까">
      <p className="small" style={{ marginTop: 0 }}>이번 주 금요일이 배당기준일이에요. 산 날을 눌러 보세요. 산 날부터 2영업일 뒤에 내 주식으로 확정돼요.</p>
      <div className="week">
        {DAYS.map((d, i) => (
          <button key={d} className={`day ${i === buy ? 'buy' : ''} ${i === settle ? 'settle' : ''} ${i === record ? 'record' : ''} ${i === record - 1 ? 'ex' : ''}`} onClick={() => setBuy(i)} aria-pressed={i === buy}>
            <b>{d}</b>
            {i === buy && <em>산 날</em>}
            {i === settle && <em>확정</em>}
            {i === record && <em>기준일</em>}
            {i === record - 1 && <em>배당락일</em>}
          </button>
        ))}
        {settle > 4 && <span className="day ghost"><b>다음 주</b><em>확정</em></span>}
      </div>
      <p className="toy-result" aria-live="polite">{ok ? `✓ 기준일 전에 확정돼서 이번 배당을 받아요` : `✕ 기준일이 지나서 확정돼요. 이번 배당은 못 받아요`}</p>
      <p className="small" style={{ margin: 0 }}>그래서 기준일 바로 전 거래일(여기서는 목요일)이 배당락일이에요. 이날부터 사면 못 받아요. 휴일이 끼면 하루씩 밀려요.</p>
    </Toy>
  )
}

/** 주주환원 바구니: 순이익을 배당·자사주 소각·남김으로 나누기 */
export function Payback() {
  const [divPct, setDivPct] = useState(30)
  const [buyPct, setBuyPct] = useState(10)
  const keep = Math.max(0, 100 - divPct - buyPct)
  const shares = 100, cancel = buyPct / 100 * 10 // 예시: 순이익 100억, 주가 10억/주 → 자사주 소각
  const left = shares - cancel
  return (
    <Toy title="주주환원 바구니">
      <div className="bar3" aria-hidden="true">
        <span style={{ width: `${divPct}%`, background: '#3D6BFF' }}>{divPct >= 18 && '배당'}</span>
        <span style={{ width: `${Math.min(buyPct, 100 - divPct)}%`, background: '#FFC93C' }}>{Math.min(buyPct, 100 - divPct) >= 18 && '자사주'}</span>
        <span style={{ width: `${keep}%`, background: '#D5DAE2' }}>{keep >= 18 && '남김'}</span>
      </div>
      <Slider label="순이익 중 배당으로" value={divPct} min={0} max={100} step={5} unit="%" onChange={v => { setDivPct(v); if (v + buyPct > 100) setBuyPct(100 - v) }} />
      <Slider label="순이익 중 자사주 사서 소각" value={buyPct} min={0} max={100 - divPct} step={5} unit="%" onChange={setBuyPct} />
      <p className="toy-result" aria-live="polite">주주환원 <b>{divPct + buyPct}%</b> · 주식 100주 → <b>{left.toLocaleString('ko-KR', { maximumFractionDigits: 1 })}주</b> (한 주의 몫 {(shares / left).toLocaleString('ko-KR', { maximumFractionDigits: 3 })}배)</p>
      <p className="small" style={{ margin: 0 }}>예시: 순이익 100억 원, 주식 100주, 주가 1주 10억 원이라고 할 때예요. 남긴 돈은 다음 투자에 써요.</p>
    </Toy>
  )
}

/** 세금 계산 길: 비과세 → 소득공제 → 과세표준 → 세율 → 세액공제 */
export function TaxFlow() {
  const [income, setIncome] = useState(5000)
  const [nontax, setNontax] = useState(200)
  const [deduct, setDeduct] = useState(1500)
  const [credit, setCredit] = useState(50)
  const base = Math.max(0, income - nontax - deduct)
  // 예시: 단일 세율 15%로 단순화
  const tax = base * 0.15, final = Math.max(0, tax - credit)
  const step = (label: string, v: number, cls = '') => <div className={`tf ${cls}`}><span>{label}</span><b>{manwon(Math.round(v))}</b></div>
  return (
    <Toy title="세금 계산 길">
      <div className="taxflow">
        {step('번 돈', income)}<i>− 비과세</i>{step('세금 매길 소득', income - nontax)}<i>− 소득공제</i>
        {step('과세표준', base, 'hl')}<i>× 세율 15%</i>{step('산출세액', tax)}<i>− 세액공제</i>{step('내야 할 세금', final, 'end')}
      </div>
      <Slider label="번 돈" value={income} min={1000} max={10000} step={100} unit="만 원" onChange={setIncome} />
      <Slider label="비과세(처음부터 빼는 돈)" value={nontax} min={0} max={1000} step={50} unit="만 원" onChange={setNontax} />
      <Slider label="소득공제" value={deduct} min={0} max={3000} step={50} unit="만 원" onChange={setDeduct} />
      <Slider label="세액공제" value={credit} min={0} max={300} step={10} unit="만 원" onChange={setCredit} />
      <p className="small" style={{ margin: 0 }}>세율을 15% 하나로 단순하게 둔 예시예요. 실제 세율은 계단처럼 올라가요(누진세율).</p>
    </Toy>
  )
}

/** 지수 만들기: 시가총액으로 무게를 둔 지수와 단순 평균 */
export function IndexMaker() {
  const firms = [
    { name: '큰 회사', cap: 600, color: '#3D6BFF' },
    { name: '중간 회사', cap: 300, color: '#19B36B' },
    { name: '작은 회사', cap: 100, color: '#FFC93C' },
  ]
  const [moves, setMoves] = useState([0, 0, 0])
  const after = firms.map((f, i) => f.cap * (1 + moves[i] / 100))
  const total = after.reduce((a, b) => a + b, 0)
  const index = total / 1000 * 100
  const simple = moves.reduce((a, b) => a + b, 0) / 3 + 100
  const W = 420, sc = 300 / 1500
  const bar = (caps: number[], y: number, label: string) => {
    let x = 110
    return (
      <g>
        <text x={104} y={y + 15} textAnchor="end" fontSize={12} fontWeight={700} fill="#6B7684">{label}</text>
        {caps.map((c, i) => { const w = c * sc, r = <rect key={i} x={x} y={y} width={w} height={22} fill={firms[i].color} stroke="#fff" strokeWidth={2} rx={4} style={{ transition: 'all .3s' }} />; x += w; return r })}
      </g>
    )
  }
  return (
    <Toy title="지수 만들기">
      <svg viewBox={`0 0 ${W} 70`} className="toy-svg" role="img" aria-label={`지수 ${index.toFixed(1)}`}>
        {bar(firms.map(f => f.cap), 4, '기준일 몸집')}
        {bar(after, 40, '오늘 몸집')}
      </svg>
      {firms.map((f, i) => (
        <Slider key={f.name} label={`${f.name} 주가 (몸집 ${f.cap}억 원)`} value={moves[i]} min={-50} max={50} step={5} unit="%" onChange={v => setMoves(m => m.map((x, j) => (j === i ? v : x)))} />
      ))}
      <div className="fx-cards">
        <div><span>몸집으로 무게를 둔 지수</span><b>{index.toFixed(1)}</b><em>코스피는 이 방식이에요</em></div>
        <div><span>세 회사를 똑같이 친 평균</span><b>{simple.toFixed(1)}</b><em>반 평균 같은 방식</em></div>
      </div>
      <p className="small" style={{ margin: 0 }}>기준일을 100으로 놓았어요. 큰 회사를 10% 올려 보고, 작은 회사를 10% 올려 보세요. 예시 숫자예요.</p>
    </Toy>
  )
}

/** ELS 길 따라가기: 조기상환 계단과 녹인 선(예시 조건: 연 6%, 녹인 50%, 3년) */
const ELS_LINES = [90, 90, 85, 85, 80, 75]
const ELS_PATHS = [
  { name: '순조롭게', pts: [100, 96, 98, 101, 103, 105, 108] },
  { name: '조금 내렸다 회복', pts: [100, 80, 82, 88, 87, 90, 95] },
  { name: '많이 내렸지만 선 위', pts: [100, 70, 58, 55, 60, 65, 70] },
  { name: '녹인 뒤 회복', pts: [100, 60, 45, 60, 70, 82, 85] },
  { name: '녹인 뒤 회복 못 함', pts: [100, 70, 45, 40, 50, 55, 60] },
]
export function ElsPath() {
  const [pick, setPick] = useState(0)
  const pts = ELS_PATHS[pick].pts
  const W = 420, H = 170, x = (i: number) => 30 + i * 62, y = (v: number) => 10 + (120 - v) / 120 * (H - 20)
  const hit = ELS_LINES.findIndex((l, i) => pts[i + 1] >= l)
  const knocked = Math.min(...pts) < 50
  const end = hit >= 0 ? hit + 1 : 6
  const result = hit >= 0
    ? { text: `${(hit + 1) * 6}개월에 조기상환: 원금 + ${(hit + 1) * 3}%`, good: true }
    : !knocked
      ? { text: '만기: 녹인 선을 안 밟아서 원금 + 18%', good: true }
      : { text: `만기: 녹인 뒤 회복 못 해서 원금 ${pts[6] - 100}%`, good: false }
  return (
    <Toy title="ELS 길 따라가기">
      <div className="chips" role="group" aria-label="지수가 움직인 길">
        {ELS_PATHS.map((p, i) => <button key={p.name} className="chip" aria-pressed={pick === i} onClick={() => setPick(i)} style={pick === i ? { background: 'var(--sea)', color: '#fff' } : undefined}>{p.name}</button>)}
      </div>
      <svg viewBox={`0 0 ${W} ${H + 16}`} className="toy-svg" role="img" aria-label={result.text}>
        <line x1={x(0)} x2={x(6)} y1={y(50)} y2={y(50)} stroke="#F2555A" strokeDasharray="5 4" />
        <text x={x(0) + 4} y={y(50) + 14} fontSize={11} fontWeight={700} fill="#F2555A">녹인 50</text>
        {ELS_LINES.map((l, i) => <line key={i} x1={x(i + 1) - 14} x2={x(i + 1) + 14} y1={y(l)} y2={y(l)} stroke="#3D6BFF" strokeWidth={3} />)}
        <polyline points={pts.slice(0, end + 1).map((v, i) => `${x(i)},${y(v)}`).join(' ')} fill="none" stroke="#191F28" strokeWidth={2.5} />
        {pts.slice(0, end + 1).map((v, i) => <circle key={i} cx={x(i)} cy={y(v)} r={4} fill={v < 50 ? '#F2555A' : '#191F28'} />)}
        {pts.map((_, i) => <text key={i} x={x(i)} y={H + 12} textAnchor="middle" fontSize={10} fill="#6B7684">{i * 6}개월</text>)}
      </svg>
      <p className="toy-result" aria-live="polite" style={{ color: result.good ? undefined : 'var(--no)' }}>{result.text}</p>
      <p className="small" style={{ margin: 0 }}>처음 지수를 100으로 놓았어요. 파란 막대는 그 평가일에 넘어야 하는 선(90·90·85·85·80·75)이에요. 예시 조건이고 실제 상품이 아니에요.</p>
    </Toy>
  )
}

/** ELD 이자 정하기(예시 조건: 참여율 50%, 최고 연 5%, 20% 넘게 오르면 1%) */
export function EldInterest() {
  const [move, setMove] = useState(8)
  const interest = move <= 0 ? 0 : move > 20 ? 1 : Math.min(5, move * 0.5)
  const W = 420, H = 120, sc = H / 145
  const col = (cx: number, base: number, top: number, topColor: string, label: string) => (
    <g>
      <rect x={cx} y={H - base * sc} width={90} height={base * sc} rx={6} fill="#C9D6FF" style={{ transition: 'all .3s' }} />
      {top > 0 && <rect x={cx} y={H - (base + top) * sc} width={90} height={top * sc} rx={6} fill={topColor} style={{ transition: 'all .3s' }} />}
      <text x={cx + 45} y={H + 16} textAnchor="middle" fontSize={12} fontWeight={700} fill="#6B7684">{label}</text>
    </g>
  )
  return (
    <Toy title="ELD 저금통 나누기">
      <svg viewBox={`0 0 ${W} ${H + 22}`} className="toy-svg" role="img" aria-label={`이자 ${interest}%`}>
        {col(60, 100, interest, '#FFC93C', 'ELD 만기')}
        {col(250, Math.max(0, 100 + Math.min(move, 0)), Math.max(move, 0), '#9DB4FF', '지수에 직접')}
      </svg>
      <Slider label="만기 때 지수 변화" value={move} min={-30} max={40} unit="%" onChange={setMove} />
      <div className="fx-cards">
        <div><span>ELD로 받는 돈 (100만 원 넣음)</span><b>{(100 + interest).toLocaleString('ko-KR')}만 원</b><em>이자 {interest}% · 원금은 그대로</em></div>
        <div><span>지수에 직접 넣었다면</span><b>{(100 + move).toLocaleString('ko-KR')}만 원</b><em>{move >= 0 ? '오른 만큼 다 받아요' : '내린 만큼 잃어요'}</em></div>
      </div>
      <p className="small" style={{ margin: 0 }}>{move > 20 ? '20% 넘게 올라서 이자가 1%로 줄었어요. ' : ''}만기까지 뒀을 때 예시예요. 세금과 수수료는 빼지 않았어요.</p>
    </Toy>
  )
}

/** ETF와 ETN 견주기 */
const ETN_EVENTS = [
  { id: 'up', name: '지수가 10% 오르면', etf: ['약 110만 원', '바구니 속 주식값이 올라요'], etn: ['약 110만 원', '약속대로 오른 만큼'] },
  { id: 'down', name: '지수가 10% 내리면', etf: ['약 90만 원', '바구니 속 주식값이 내려요'], etn: ['약 90만 원', '약속대로 내린 만큼'] },
  { id: 'trouble', name: '만든 회사가 어려워지면', etf: ['바구니는 그대로', '주식은 따로 맡겨 둬서 내 몫이 남아요'], etn: ['약속이 흔들려요', '증권사가 못 갚으면 돌려받기 어려울 수 있어요'] },
]
export function EtfEtn() {
  const [ev, setEv] = useState(0)
  const e = ETN_EVENTS[ev]
  return (
    <Toy title="ETF와 ETN 견주기">
      <p className="small" style={{ margin: '0 0 8px' }}>둘 다 같은 지수를 따라가고, 각각 100만 원어치 샀다고 해 봐요.</p>
      <div className="chips" role="group" aria-label="일어난 일">
        {ETN_EVENTS.map((x, i) => <button key={x.id} className="chip" aria-pressed={ev === i} onClick={() => setEv(i)} style={ev === i ? { background: 'var(--sea)', color: '#fff' } : undefined}>{x.name}</button>)}
      </div>
      <div className="fx-cards" aria-live="polite">
        <div><span>🧺 ETF · 운용사가 산 주식 바구니</span><b>{e.etf[0]}</b><em>{e.etf[1]}</em></div>
        <div><span>📜 ETN · 증권사의 약속</span><b style={e.id === 'trouble' ? { color: 'var(--no)' } : undefined}>{e.etn[0]}</b><em>{e.etn[1]}</em></div>
      </div>
      <p className="small" style={{ margin: 0 }}>수수료와 세금은 뺀 예시예요. 시장 가격이 원래 값과 벌어지는 일(괴리)도 따로 있어요.</p>
    </Toy>
  )
}

const pickStyle = (on: boolean) => (on ? { background: 'var(--sea)', color: '#fff' } : undefined)

/** 주주총회 표 세기: 주식 100주 회사의 보통결의·특별결의 */
export function Meeting() {
  const [attend, setAttend] = useState(40)
  const [yes, setYes] = useState(30)
  const y = Math.min(yes, attend)
  const ordinary = y > attend / 2 && y >= 25
  const special = y >= attend * 2 / 3 && y >= 100 / 3
  return (
    <Toy title="주주총회 표 세기">
      <svg viewBox="0 0 420 92" className="toy-svg" role="img" aria-label={`100주 중 ${attend}주 출석, ${y}주 찬성`}>
        {Array.from({ length: 100 }, (_, i) => (
          <circle key={i} cx={12 + (i % 25) * 16.4} cy={12 + Math.floor(i / 25) * 22} r={6.5}
            fill={i < y ? '#3D6BFF' : i < attend ? '#FFB3B5' : '#E5E8EB'} style={{ transition: 'fill .2s' }} />
        ))}
      </svg>
      <p className="small" style={{ margin: '0 0 6px' }}>● 파랑 찬성 · ● 분홍 출석했지만 반대 · ● 회색 오지 않음 (주식 100주, 1주에 1표)</p>
      <Slider label="출석한 주식" value={attend} min={0} max={100} unit="주" onChange={setAttend} />
      <Slider label="찬성한 주식" value={y} min={0} max={attend} unit="주" onChange={setYes} />
      <div className="fx-cards" aria-live="polite">
        <div><span>보통결의 (출석 과반수 + 전체 4분의 1 이상)</span><b style={{ color: ordinary ? 'var(--ok)' : 'var(--no)' }}>{ordinary ? '통과' : '통과 못 함'}</b><em>{y > attend / 2 ? '출석 과반수 ✓' : '출석 과반수 ✗'} · {y >= 25 ? '25주 이상 ✓' : '25주 이상 ✗'}</em></div>
        <div><span>특별결의 (출석 3분의 2 + 전체 3분의 1 이상)</span><b style={{ color: special ? 'var(--ok)' : 'var(--no)' }}>{special ? '통과' : '통과 못 함'}</b><em>{y >= attend * 2 / 3 ? '출석 3분의 2 ✓' : '출석 3분의 2 ✗'} · {y >= 100 / 3 ? '34주 이상 ✓' : '34주 이상 ✗'}</em></div>
      </div>
    </Toy>
  )
}

/** 피자 다시 자르기: 주식분할·병합 (예시: 12주, 1주 10만 원, 주당배당금 1,000원) */
const SPLITS = [
  { name: '그대로', k: 1 }, { name: '1주 → 2주', k: 2 }, { name: '1주 → 5주', k: 5 }, { name: '5주 → 1주 (병합)', k: 1 / 5 },
]
export function Splitter() {
  const [pick, setPick] = useState(2)
  const { k } = SPLITS[pick]
  const raw = 12 * k, shares = Math.floor(raw + 1e-9), odd = raw - shares
  const price = 100000 / k, dps = 1000 / k
  const slices = Math.max(2, Math.min(40, Math.round(8 * k)))
  const cx = 70, cy = 70, r = 60
  return (
    <Toy title="피자 다시 자르기">
      <div className="chips" role="group" aria-label="자르는 방법">
        {SPLITS.map((s, i) => <button key={s.name} className="chip" aria-pressed={pick === i} onClick={() => setPick(i)} style={pickStyle(pick === i)}>{s.name}</button>)}
      </div>
      <div className="split-row">
        <svg viewBox="0 0 140 140" width={140} height={140} role="img" aria-label={`피자 ${slices}조각`}>
          <circle cx={cx} cy={cy} r={r} fill="#FFC93C" />
          <path d={`M${cx},${cy} L${cx},${cy - r} A${r},${r} 0 0,1 ${cx + r},${cy} Z`} fill="#E26B3A" />
          {Array.from({ length: slices }, (_, i) => {
            const a = (i / slices) * 2 * Math.PI
            return <line key={i} x1={cx} y1={cy} x2={cx + r * Math.sin(a)} y2={cy - r * Math.cos(a)} stroke="#fff" strokeWidth={1.5} />
          })}
        </svg>
        <div className="fx-cards" style={{ flex: 1, margin: 0 }}>
          <div><span>내 주식</span><b>{shares.toLocaleString('ko-KR')}주</b><em>{odd > 0 ? `자투리 ${Math.round(odd / k)}주는 돈으로` : '처음엔 12주'}</em></div>
          <div><span>1주 값</span><b>{won(price)}</b><em>처음엔 10만 원</em></div>
          <div><span>내 몫 (주식 + 자투리 돈)</span><b>{won(12 * 100000)}</b><em>그대로예요</em></div>
          <div><span>주당배당금 → 받는 배당</span><b>{won(dps)}</b><em>모두 {won(12 * 1000)} 그대로</em></div>
        </div>
      </div>
      <p className="small" style={{ margin: 0 }}>주황 조각이 내 몫(회사의 4분의 1)이에요. 조각을 몇 개로 자르든 양은 같아요. 예시 숫자예요.</p>
    </Toy>
  )
}

/** 두 가게 합치기: 합병비율 (예시: A 1주 가치 6,000원, B 1주 가치 12,000원, A 100주 보유) */
export function Merger() {
  const [ratio, setRatio] = useState(0.5)
  const aVal = 6000, bVal = 12000, mine = 100
  const got = mine * ratio, after = got * bVal, before = mine * aVal, diff = after - before
  return (
    <Toy title="두 가게 합치기">
      <div className="fx-cards">
        <div><span>🍙 A가게 (없어지는 회사)</span><b>1주 {won(aVal)}</b><em>내가 100주 가졌어요</em></div>
        <div><span>🍢 B가게 (남는 회사)</span><b>1주 {won(bVal)}</b><em>A를 품어요</em></div>
      </div>
      <Slider label="합병비율: A 1주 → B" value={ratio} min={0.2} max={1} step={0.05} unit="주" onChange={setRatio} />
      <p className="toy-result" aria-live="polite">A 100주 → B <b>{got.toLocaleString('ko-KR', { maximumFractionDigits: 1 })}주</b> · 가치 {won(after)} ({diff === 0 ? '그대로' : diff > 0 ? `${won(diff)} 이득` : `${won(-diff)} 손해`})</p>
      <p className="small" style={{ margin: 0 }}>두 회사 1주 가치로 맞추면 0.5주가 공평해요. 비율이 A에 유리하면 B 주주가, B에 유리하면 A 주주가 손해를 봐요. 예시 숫자예요.</p>
    </Toy>
  )
}

/** 공모주 나눠 받기: 균등배정·비례배정 (글의 예시: 공모가 1만 원, 개인 청약 1만 주를 절반씩 균등·비례로) */
export function Ipo() {
  const [mine, setMine] = useState(1000)
  const [comp, setComp] = useState(100)
  const [people, setPeople] = useState(1000)
  const price = 10000, total = 10000, even = total / 2, prop = total / 2
  const asked = total * comp // 모두가 청약한 주식 수
  const evenEach = even / people
  const propMine = prop * mine / asked
  const deposit = mine * price / 2
  const evenText = evenEach >= 1 ? `${Math.floor(evenEach)}주쯤` : `1주 받을 확률 약 ${Math.round(evenEach * 100)}%`
  return (
    <Toy title="공모주 나눠 받기">
      <Slider label="내가 청약한 주식" value={mine} min={10} max={5000} step={10} unit="주" onChange={setMine} />
      <Slider label="경쟁률" value={comp} min={10} max={2000} step={10} unit=" 대 1" onChange={setComp} />
      <Slider label="최소 수량 이상 청약한 사람" value={people} min={100} max={50000} step={100} unit="명" onChange={setPeople} />
      <div className="fx-cards" aria-live="polite">
        <div><span>먼저 내는 증거금 (절반)</span><b>{won(deposit)}</b><em>못 받은 만큼은 돌려받아요</em></div>
        <div><span>균등배정 (똑같이 나눔)</span><b>{evenText}</b><em>얼마를 넣든 같아요</em></div>
        <div><span>비례배정 (넣은 만큼)</span><b>{propMine.toLocaleString('ko-KR', { maximumFractionDigits: 2 })}주</b><em>많이 넣을수록 늘어요</em></div>
        <div><span>모두 합쳐 받는 주식</span><b>{(Math.floor(evenEach) + Math.floor(propMine)).toLocaleString('ko-KR')}주쯤</b><em>나머지 증거금은 돌려받아요</em></div>
      </div>
      <p className="small" style={{ margin: 0 }}>공모가 1만 원, 개인 청약 1만 주를 절반은 균등, 절반은 비례로 나눈 예시예요. 실제 배정 방법과 끝수 처리는 증권회사·공모마다 달라요.</p>
    </Toy>
  )
}

/** 상장폐지 가는 길: 단계별로 내 주식에 생기는 일 */
const DELIST_STEPS = [
  { name: '경고 딱지', title: '관리종목 지정', trade: '사고팔 수 있어요', text: '문제가 생기면 거래소가 "조심하세요" 딱지를 붙여요. 이때 고치면 딱지가 떨어지기도 해요.' },
  { name: '거래 멈춤', title: '매매거래정지', trade: '사고팔 수 없어요', text: '중대한 문제가 드러나면 거래가 멈춰요. 내 주식은 그대로지만 팔 수 없어 돈이 묶여요.' },
  { name: '심사', title: '심사와 개선기간', trade: '대개 멈춘 채예요', text: '거래소가 계속 상장해도 될지 살펴보고, 회사에 고칠 시간을 주기도 해요. 회사는 이의를 낼 수 있어요.' },
  { name: '결정', title: '상장폐지 결정', trade: '곧 마지막 거래', text: '고치지 못하면 상장폐지가 정해져요. 회사가 없어지는 건 아니에요.' },
  { name: '마지막 장', title: '정리매매', trade: '며칠만 사고팔 수 있어요', text: '거래소를 떠나기 전 마지막으로 사고팔 기회예요. 팔려는 사람이 몰려 값이 크게 떨어지기 쉬워요.' },
  { name: '그 뒤', title: '상장폐지 뒤', trade: '거래소에서는 못 사고팔아요', text: '주식은 여전히 내 것이지만, 장외에서 살 사람을 찾기가 아주 어려워요.' },
]
export function DelistPath() {
  const [step, setStep] = useState(0)
  const s = DELIST_STEPS[step]
  return (
    <Toy title="상장폐지 가는 길">
      <ol className="steps-mini" aria-label="단계">
        {DELIST_STEPS.map((d, i) => (
          <li key={d.name}><button className={i === step ? 'on' : i < step ? 'done' : ''} aria-current={i === step ? 'step' : undefined} onClick={() => setStep(i)}><span>{i + 1}</span>{d.name}</button></li>
        ))}
      </ol>
      <div className="fx-cards" aria-live="polite">
        <div><span>{step + 1}단계</span><b>{s.title}</b><em>{s.text}</em></div>
        <div><span>내 주식</span><b style={{ color: step === 0 ? undefined : 'var(--no)' }}>{s.trade}</b><em>{step < 5 ? '회사가 살아나면 다시 돌아오기도 해요' : '그래서 앞 단계에서 미리 살펴봐야 해요'}</em></div>
      </div>
      <div className="chips">
        <button className="chip" disabled={step === 0} onClick={() => setStep(step - 1)}>이전 단계</button>
        <button className="chip" disabled={step === DELIST_STEPS.length - 1} onClick={() => setStep(step + 1)}>다음 단계</button>
      </div>
      <p className="small" style={{ margin: '8px 0 0' }}>흔한 흐름을 줄여 그린 그림이에요. 사유에 따라 단계를 건너뛰거나 순서가 다를 수 있어요.</p>
    </Toy>
  )
}

/** 남은 돈 나눠 갖기 순서: 파산 때 갚는 순서 (예시 금액, 억 원) */
const CLAIMS = [
  { name: '담보 잡은 채권자', amount: 40, color: '#3D6BFF' },
  { name: '세금·밀린 임금', amount: 10, color: '#19B36B' },
  { name: '일반 채권자', amount: 100, color: '#E0A500' },
]
export function Waterfall() {
  const [left, setLeft] = useState(100)
  let rest = left
  const rows = CLAIMS.map(c => { const got = Math.min(rest, c.amount); rest -= got; return { ...c, got } })
  const owners = rest
  return (
    <Toy title="남은 돈 나눠 갖기 순서">
      <Slider label="회사를 정리하고 남은 재산" value={left} min={0} max={200} step={5} unit="억 원" onChange={setLeft} />
      <div className="pay-rows" aria-live="polite">
        {rows.map((r, i) => (
          <div key={r.name}>
            <span>{i + 1}. {r.name}</span>
            <i><b style={{ width: `${r.got / r.amount * 100}%`, background: r.color }} /></i>
            <em>{r.got}억 / {r.amount}억</em>
          </div>
        ))}
        <div><span>4. 주주</span><strong style={{ color: owners > 0 ? 'var(--sea)' : 'var(--no)' }}>{owners > 0 ? `${owners}억 원 남아요` : '남는 돈이 없어요'}</strong></div>
      </div>
      <p className="toy-result" aria-live="polite">빚이 모두 150억 원이에요. {owners > 0 ? '빚을 다 갚고 남아야 주주에게 돌아가요.' : '앞 순서가 다 받기 전에는 주주는 받지 못해요.'}</p>
      <p className="small" style={{ margin: 0 }}>예시 금액이에요. 실제로는 최근 몇 달 치 임금처럼 담보보다 먼저 받는 돈도 있어서, 순서는 법과 경우에 따라 더 복잡해요.</p>
    </Toy>
  )
}

/** 주식 늘리고 줄이기: 유상증자·무상증자·유상감자·무상감자 (예시: 100주, 1주 1만 원, 내 10주) */
const CAPITAL_ACTIONS = [
  { id: 'paidin', name: '유상증자', line: '1주당 0.5주를 8천 원에 새로 팔아요' },
  { id: 'bonus', name: '무상증자', line: '1주당 1주를 공짜로 줘요' },
  { id: 'paidout', name: '유상감자', line: '2주를 1주로 줄이고 없앤 주식마다 1만 원을 돌려줘요' },
  { id: 'reduce', name: '무상감자', line: '5주를 1주로 줄이고 돈은 주지 않아요' },
] as const
export function Capital() {
  const [pick, setPick] = useState(0)
  const [join, setJoin] = useState(true)
  const a = CAPITAL_ACTIONS[pick]
  // 회사 가치(만 원)·주식 수·내 주식·내가 내거나 받은 돈(원)
  let value = 100, shares = 100, mineShares = 10, cashIn = 0, cashOut = 0, flow = '그대로'
  if (a.id === 'paidin') { shares = 150; value = 100 + 50 * 0.8; flow = '+40만 원 들어와요'; if (join) { mineShares = 15; cashOut = 5 * 8000 } }
  if (a.id === 'bonus') { shares = 200; mineShares = 20 }
  if (a.id === 'paidout') { shares = 50; value = 50; mineShares = 5; cashIn = 5 * 10000; flow = '−50만 원 나가요' }
  if (a.id === 'reduce') { shares = 20; mineShares = 2 }
  const price = value * 10000 / shares
  const mine = mineShares * price + cashIn - cashOut
  const pct = mineShares / shares * 100
  return (
    <Toy title="주식 늘리고 줄이기">
      <div className="chips" role="group" aria-label="고르기">
        {CAPITAL_ACTIONS.map((x, i) => <button key={x.id} className="chip" aria-pressed={pick === i} onClick={() => setPick(i)} style={pickStyle(pick === i)}>{x.name}</button>)}
      </div>
      <p className="small" style={{ margin: '8px 0' }}>{a.line}</p>
      {a.id === 'paidin' && (
        <label className="toggle" style={{ marginBottom: 6 }}><input type="checkbox" checked={join} onChange={e => setJoin(e.target.checked)} /> 나도 새 주식 5주를 사요 (4만 원)</label>
      )}
      <div className="fx-cards" aria-live="polite">
        <div><span>회사 돈</span><b>{flow}</b><em>회사 가치 {value.toLocaleString('ko-KR')}만 원</em></div>
        <div><span>주식 수 → 1주 값</span><b>{shares}주 · {won(Math.round(price))}</b><em>처음엔 100주 · 1만 원</em></div>
        <div><span>내 주식 (비율)</span><b>{mineShares}주 ({pct.toLocaleString('ko-KR', { maximumFractionDigits: 1 })}%)</b><em>처음엔 10주 (10%)</em></div>
        <div><span>내 몫 (주식 + 받은 돈 − 낸 돈)</span><b style={{ color: Math.round(mine) < 100000 ? 'var(--no)' : undefined }}>{won(Math.round(mine))}</b><em>{Math.round(mine) < 100000 ? '안 사서 비율이 줄었어요(희석)' : '처음 10만 원과 같아요'}</em></div>
      </div>
      <p className="small" style={{ margin: 0 }}>1주 값은 권리락으로 맞춰진 이론값이에요. 실제 주가는 소식과 기대에 따라 따로 움직여요. 신주인수권을 팔아 손해를 줄이는 방법은 그림에서 뺐어요.</p>
    </Toy>
  )
}

/** 가게 장부 써 보기: 손익계산서와 재무상태표 (예시: 처음 내 돈 200만 원, 판 돈은 모두 현금으로 받았다고 가정) */
export function Ledger() {
  const [sales, setSales] = useState(500)
  const [cost, setCost] = useState(400)
  const [loan, setLoan] = useState(100)
  const start = 200, profit = sales - cost
  const equity = start + profit, assets = Math.max(0, equity + loan)
  const W = 420, top = Math.max(assets, loan + Math.max(equity, 0), 1), sc = 260 / Math.max(top, 600)
  return (
    <Toy title="가게 장부 써 보기">
      <Slider label="1년 동안 판 돈 (매출)" value={sales} min={0} max={1000} step={10} unit="만 원" onChange={setSales} />
      <Slider label="재료·월세·월급 (비용)" value={cost} min={0} max={1000} step={10} unit="만 원" onChange={setCost} />
      <Slider label="은행에서 빌린 돈" value={loan} min={0} max={400} step={10} unit="만 원" onChange={setLoan} />
      <div className="fx-cards" aria-live="polite">
        <div><span>손익계산서 (1년 동안)</span><b style={{ color: profit < 0 ? 'var(--no)' : undefined }}>이익 {profit.toLocaleString('ko-KR')}만 원</b><em>매출 {sales} − 비용 {cost}</em></div>
        <div><span>재무상태표 (12월 31일)</span><b>자산 {assets.toLocaleString('ko-KR')}만 원</b><em>부채 {loan} + 자본 {equity}</em></div>
      </div>
      <svg viewBox={`0 0 ${W} 70`} className="toy-svg" role="img" aria-label={`자산 ${assets}만 원, 부채 ${loan}만 원, 자본 ${equity}만 원`}>
        <text x={0} y={18} fontSize={12} fontWeight={700} fill="#6B7684">가진 것</text>
        <rect x={60} y={4} width={assets * sc} height={20} rx={6} fill="#3D6BFF" style={{ transition: 'width .3s' }} />
        <text x={0} y={54} fontSize={12} fontWeight={700} fill="#6B7684">어디서</text>
        <rect x={60} y={40} width={loan * sc} height={20} rx={6} fill="#F2555A" style={{ transition: 'width .3s' }} />
        <rect x={60 + loan * sc} y={40} width={Math.max(equity, 0) * sc} height={20} rx={6} fill="#19B36B" style={{ transition: 'all .3s' }} />
      </svg>
      <p className="small" style={{ margin: 0 }}>● 빨강 부채(빌린 돈) ● 초록 자본(처음 낸 200만 원 + 이익). 이익이 나면 자본이 늘고, 손해가 나면 줄어요. {equity < 0 ? '자본이 0보다 작아졌어요. 가진 것보다 빚이 많은 상태예요(자본잠식).' : ''}</p>
    </Toy>
  )
}

/** 이 소식은 어느 공시? */
const NEWS = [
  { text: '1년 장사를 마치고 재무제표와 사업 내용을 정리했어요', answer: '정기공시', options: ['정기공시', '조회공시', '지분공시'], why: '사업보고서예요. 해마다 정해진 때에 꼭 내요.' },
  { text: '이사회에서 1주에 500원씩 배당하기로 정했어요', answer: '수시공시', options: ['발행공시', '수시공시', '정기공시'], why: '배당 결정은 정해지면 바로 알리는 수시공시예요.' },
  { text: '새 주식을 팔아 돈을 모으기로 정했어요 (유상증자)', answer: '주요사항보고서', options: ['공정공시', '주요사항보고서', '조회공시'], why: '증자·감자·합병처럼 회사 모양을 바꾸는 일은 주요사항보고서로 알려요.' },
  { text: '"큰 회사에 팔린대!" 소문에 주가가 크게 올라 거래소가 물었어요', answer: '조회공시', options: ['조회공시', '정기공시', '발행공시'], why: '거래소의 질문에 회사가 "사실인지" 답하는 조회공시예요.' },
  { text: '내년 실적 전망을 투자자 모임에서 말하려고 해요', answer: '공정공시', options: ['지분공시', '공정공시', '수시공시'], why: '몇몇 사람에게만 먼저 말하지 않게, 모두에게 동시에 알리는 공정공시예요.' },
  { text: '어떤 회사가 우리 회사 주식을 5% 넘게 샀어요', answer: '지분공시', options: ['지분공시', '주요사항보고서', '정기공시'], why: '5% 대량보유 보고는 누가 얼마나 가졌는지 알리는 지분공시예요.' },
  { text: '새 주식을 여러 사람에게 팔기 전에 조건을 적어 냈어요', answer: '발행공시', options: ['수시공시', '조회공시', '발행공시'], why: '증권신고서 같은 발행공시예요. 무엇을 어떤 조건으로 파는지 미리 알려요.' },
]
export function DisclosureSort() {
  const [i, setI] = useState(0)
  const [chosen, setChosen] = useState<string | null>(null)
  const [score, setScore] = useState(0)
  const n = NEWS[i % NEWS.length]
  const done = i >= NEWS.length
  const choose = (o: string) => { if (chosen) return; setChosen(o); if (o === n.answer) setScore(score + 1) }
  const next = () => { setChosen(null); setI(i + 1) }
  if (done) {
    return (
      <Toy title="이 소식은 어느 공시?">
        <p className="toy-result">{NEWS.length}개 중 <b>{score}개</b> 맞혔어요!</p>
        <button className="chip" onClick={() => { setI(0); setScore(0); setChosen(null) }}>처음부터 다시</button>
      </Toy>
    )
  }
  return (
    <Toy title="이 소식은 어느 공시?">
      <p className="small" style={{ margin: '0 0 4px' }}>소식 {i + 1} / {NEWS.length}</p>
      <p className="toy-result" style={{ marginTop: 0 }}>📰 {n.text}</p>
      <div className="chips" role="group" aria-label="공시 고르기">
        {n.options.map(o => (
          <button key={o} className="chip" onClick={() => choose(o)} aria-pressed={chosen === o}
            style={chosen ? (o === n.answer ? { background: 'var(--ok)', color: '#fff' } : o === chosen ? { background: 'var(--no)', color: '#fff' } : { opacity: 0.5 }) : undefined}>{o}</button>
        ))}
      </div>
      {chosen && (
        <p aria-live="polite" style={{ margin: '10px 0 0', fontWeight: 700 }}>
          {chosen === n.answer ? '맞아요! ' : `아쉬워요. 답은 ${n.answer}예요. `}{n.why}{' '}
          <button className="chip" onClick={next}>{i + 1 < NEWS.length ? '다음 소식' : '결과 보기'}</button>
        </p>
      )}
    </Toy>
  )
}

/** 기준금리 손잡이: 올리고 내릴 때 대개 생기는 일(경향). 대출 1억 원·예금 1천만 원 예시 */
export function RateMachine() {
  const [d, setD] = useState(0.5)
  const up = d > 0, flat = d === 0
  const arrow = (dir: 1 | -1) => (flat ? '→ 그대로' : (up ? dir : -dir) > 0 ? '↑ 늘어나는 쪽' : '↓ 줄어드는 쪽')
  const rows: [string, string, string][] = [
    ['🏦 대출 이자 (1억 원)', arrow(1), flat ? '변화 없음' : `1년 약 ${up ? '+' : '−'}${won(Math.abs(d) * 1_000_000)}`],
    ['🐷 예금 이자 (1천만 원)', arrow(1), flat ? '변화 없음' : `1년 약 ${up ? '+' : '−'}${won(Math.abs(d) * 100_000)}`],
    ['🛒 쓰고 투자하는 돈', arrow(-1), up ? '빌리기 부담돼 덜 써요' : flat ? '' : '빌리기 쉬워 더 써요'],
    ['🍎 물가 오름', arrow(-1), up ? '천천히 식어요' : flat ? '' : '천천히 데워져요'],
    ['💱 원화 값', arrow(1), up ? '강해지는 경향' : flat ? '' : '약해지는 경향'],
  ]
  return (
    <Toy title="기준금리 손잡이">
      <Slider label="기준금리 바꾸기" value={d} min={-1} max={1} step={0.25} unit="%p" onChange={setD} />
      <div className="rate-rows" aria-live="polite">
        {rows.map(([k, a, note]) => (
          <div key={k}><span>{k}</span><b style={{ color: flat ? undefined : a.startsWith('↑') ? 'var(--sea)' : 'var(--no)' }}>{a}</b><em>{note}</em></div>
        ))}
      </div>
      <p className="small" style={{ margin: 0 }}>은행 금리가 기준금리만큼 똑같이 움직였다고 가정한 예시예요. 화살표는 대개 그렇다는 경향이고, 효과는 몇 달에서 1년 넘게 걸려 천천히 와요.</p>
    </Toy>
  )
}

/** 시장 브레이크 걸기: 하루 지수 변동에 따라 걸리는 장치 (선물도 같은 만큼 움직였다고 가정, 1분 넘게 이어졌다고 봄) */
export function Brakes() {
  const [move, setMove] = useState(-6)
  const drop = -move
  const items = [
    { name: '사이드카', on: Math.abs(move) >= 5, what: '프로그램 매매 주문 5분 멈춤', when: '선물 5% 넘게 움직임' },
    { name: '서킷브레이커 1단계', on: drop >= 8, what: '시장 전체 20분 멈춤', when: '지수 8% 넘게 떨어짐' },
    { name: '서킷브레이커 2단계', on: drop >= 15, what: '시장 전체 다시 20분 멈춤', when: '지수 15% 넘게 떨어짐' },
    { name: '서킷브레이커 3단계', on: drop >= 20, what: '그날 시장 닫음', when: '지수 20% 넘게 떨어짐' },
  ]
  return (
    <Toy title="시장 브레이크 걸기">
      <Slider label="오늘 지수가 전날보다" value={move} min={-25} max={10} step={1} unit="%" onChange={setMove} />
      <div className="rate-rows" aria-live="polite">
        {items.map(x => (
          <div key={x.name}><span>{x.on ? '🔴' : '⚪'} {x.name}</span><b style={{ color: x.on ? 'var(--no)' : 'var(--gray)' }}>{x.on ? x.what : '안 걸려요'}</b><em>{x.when}</em></div>
        ))}
      </div>
      <p className="small" style={{ margin: 0 }}>{move > 0 ? '오를 때는 서킷브레이커가 걸리지 않고, 사이드카만 걸릴 수 있어요. ' : ''}코스피 기준의 줄인 예시예요. 각 장치는 하루에 한 번씩만 걸리고, 장 마감이 가까우면 걸리지 않는 등 자세한 기준이 더 있어요.</p>
    </Toy>
  )
}

/** ISA 바구니에 담아 보기: 3년 동안 번 이자·배당 순이익에 붙는 세금 견주기 (조세특례제한법 제91조의18, 소득세법 제129조) */
const ISA_LIMITS = [{ name: '일반형', limit: 200 }, { name: '서민형·농어민', limit: 400 }]
export function IsaBox() {
  const [profit, setProfit] = useState(300)
  const [pick, setPick] = useState(0)
  const limit = ISA_LIMITS[pick].limit
  const normal = profit * 0.154
  const taxed = Math.max(0, profit - limit)
  const isa = taxed * 0.099
  const man = (v: number) => `${v.toLocaleString('ko-KR', { maximumFractionDigits: 1 })}만 원`
  return (
    <Toy title="ISA 바구니에 담아 보기">
      <div className="chips" role="group" aria-label="ISA 종류">
        {ISA_LIMITS.map((x, i) => <button key={x.name} className="chip" aria-pressed={pick === i} onClick={() => setPick(i)} style={pickStyle(pick === i)}>{x.name}</button>)}
      </div>
      <Slider label="3년 동안 번 이자·배당(순이익)" value={profit} min={0} max={1000} step={50} unit="만 원" onChange={setProfit} />
      <div className="fx-cards" aria-live="polite">
        <div><span>🏦 보통 계좌 (받을 때마다 15.4%)</span><b>{man(normal)}</b><em>순이익 전부에 세금</em></div>
        <div><span>🧺 ISA (비과세 {man(limit)}, 넘으면 9.9%)</span><b>{man(isa)}</b><em>{taxed > 0 ? `넘은 ${man(taxed)}에만 세금` : '한도 안이라 세금 없음'}</em></div>
      </div>
      <p className="toy-result">ISA에서 덜 내는 세금 <b>{man(normal - isa)}</b></p>
      <p className="small" style={{ margin: 0 }}>지방소득세까지 넣은 예시예요. 보통 계좌는 금융소득이 1년 2천만 원을 넘어 종합과세되는 경우를 넣지 않았어요. 3년을 채우지 못하면 ISA 혜택은 없어요.</p>
    </Toy>
  )
}

/** 연금 세액공제 계산: 연금저축 600만 원, IRP와 합쳐 900만 원까지 12% 또는 15% (소득세법 제59조의3) */
const PENSION_RATES = [{ name: '총급여 5,500만 원 이하', rate: 15 }, { name: '총급여 5,500만 원 초과', rate: 12 }]
export function PensionCredit() {
  const [saving, setSaving] = useState(400)
  const [irp, setIrp] = useState(300)
  const [pick, setPick] = useState(0)
  const rate = PENSION_RATES[pick].rate
  const base = Math.min(Math.min(saving, 600) + irp, 900)
  const out = saving + irp - base
  const credit = base * rate / 100
  const man = (v: number) => `${v.toLocaleString('ko-KR', { maximumFractionDigits: 1 })}만 원`
  return (
    <Toy title="연금 세액공제 계산">
      <div className="chips" role="group" aria-label="소득 구간">
        {PENSION_RATES.map((x, i) => <button key={x.name} className="chip" aria-pressed={pick === i} onClick={() => setPick(i)} style={pickStyle(pick === i)}>{x.name}</button>)}
      </div>
      <Slider label="연금저축에 1년 동안 넣은 돈" value={saving} min={0} max={1200} step={50} unit="만 원" onChange={setSaving} />
      <Slider label="IRP에 1년 동안 넣은 돈" value={irp} min={0} max={1200} step={50} unit="만 원" onChange={setIrp} />
      <div className="fx-cards" aria-live="polite">
        <div><span>세액공제 셈에 넣는 돈</span><b>{man(base)}</b><em>{out > 0 ? `한도를 넘은 ${man(out)}은 빠져요` : '모두 셈에 들어가요'}</em></div>
        <div><span>소득세에서 빼 주는 돈 ({rate}%)</span><b>{man(credit)}</b><em>지방소득세까지 치면 {man(credit * 1.1)}</em></div>
      </div>
      <p className="small" style={{ margin: 0 }}>근로소득만 있는 사람 기준 예시예요. 다른 소득이 있으면 종합소득금액 4,500만 원으로 나눠요. 낼 세금보다 많이 빼 주지는 않고, 만기 ISA에서 옮긴 돈의 추가 한도는 넣지 않았어요.</p>
    </Toy>
  )
}

/** 예금 vs 적금: 같은 금리, 같은 1년 동안 같은 금액을 모을 때 이자 (단리, 세금 15.4% 뺀 값도) */
export function Deposit() {
  const [rate, setRate] = useState(5)
  const [monthly, setMonthly] = useState(100)
  const total = monthly * 12
  const lump = total * rate / 100 // 정기예금: 첫날 전부 넣고 12달
  const install = monthly * rate / 100 * (12 * 13 / 2) / 12 // 적금: n번째 달 넣은 돈은 (13 - n)달 맡김
  const asDeposit = total ? install / total * 100 : 0
  const after = (v: number) => v * (1 - 0.154)
  const max = Math.max(lump, 1)
  const bars = [
    { name: '정기예금', sub: `첫날 ${total.toLocaleString('ko-KR')}만 원`, v: lump, color: '#3D6BFF' },
    { name: '적금', sub: `매달 ${monthly.toLocaleString('ko-KR')}만 원`, v: install, color: '#FFC93C' },
  ]
  return (
    <Toy title="예금 vs 적금 이자 견주기">
      <div className="toy-bars">
        {bars.map(b => (
          <div key={b.name} className="toy-bar-row">
            <span><b>{b.name}</b> <small>{b.sub}</small></span>
            <i style={{ width: `${Math.max(3, b.v / max * 100)}%`, background: b.color }} />
            <b className="num">{b.v.toLocaleString('ko-KR', { maximumFractionDigits: 1 })}만 원</b>
          </div>
        ))}
      </div>
      <Slider label="금리(1년)" value={rate} min={0.5} max={10} step={0.5} unit="%" onChange={setRate} />
      <Slider label="매달 넣는 돈" value={monthly} min={10} max={300} step={10} unit="만 원" onChange={setMonthly} />
      <p className="toy-result" aria-live="polite">적금 {rate}%는 1년 동안 모은 {total.toLocaleString('ko-KR')}만 원 전체로 치면 <b>예금 {asDeposit.toFixed(2)}%</b>와 이자가 같아요. 세금 15.4%를 떼면 예금 {after(lump).toLocaleString('ko-KR', { maximumFractionDigits: 1 })}만 원, 적금 {after(install).toLocaleString('ko-KR', { maximumFractionDigits: 1 })}만 원이에요.</p>
      <p className="small" style={{ margin: 0 }}>1년 만기, 단리, 매달 같은 날 넣는다고 본 예시예요. 실제 이자는 상품마다 달라요.</p>
    </Toy>
  )
}

// 돈 맡길 곳 견주기: 상품 이름이 아니라 통장 종류. 보호·원금은 예금보험공사 보호대상 금융상품 안내와 금융위원회 보도자료(2025. 11. 19.)
const SHELF = [
  { key: 'normal', icon: '👛', name: '보통예금', where: '은행', guard: '예금보험공사 1억 원까지', guardOk: true, out: '아무 때나', interest: '정해짐(아주 낮음)' },
  { key: 'fixed', icon: '🔒', name: '정기예금', where: '은행', guard: '예금보험공사 1억 원까지', guardOk: true, out: '만기에(깨면 이자 줄어요)', interest: '정해짐' },
  { key: 'saving', icon: '🐷', name: '적금', where: '은행', guard: '예금보험공사 1억 원까지', guardOk: true, out: '만기에(깨면 이자 줄어요)', interest: '정해짐' },
  { key: 'cma', icon: '🅿️', name: 'CMA (증권사 RP·MMF·발행어음형)', where: '증권사', guard: '보호 대상 아님', guardOk: false, out: '아무 때나', interest: 'RP·발행어음형은 약정 수익률, MMF형은 굴린 만큼' },
  { key: 'cma-j', icon: '🏢', name: 'CMA (종금형)', where: '종합금융회사', guard: '예금보험공사 1억 원까지', guardOk: true, out: '아무 때나', interest: '굴린 만큼' },
  { key: 'ima', icon: '🏗️', name: 'IMA', where: '자기자본 8조 원 넘는 증권사', guard: '예금보험 아님 · 만기 원금은 증권사가 지급', guardOk: false, out: '만기에(깨면 원금 약속 없음)', interest: '굴린 만큼(실적배당)' },
]
export function Shelf() {
  const [pick, setPick] = useState('cma')
  const s = SHELF.find(x => x.key === pick)!
  return (
    <Toy title="돈 맡길 곳 견주기">
      <div className="toy-chips" role="radiogroup" aria-label="통장 고르기">
        {SHELF.map(x => (
          <button key={x.key} type="button" role="radio" aria-checked={pick === x.key} className={`chip${pick === x.key ? ' chip--on' : ''}`} onClick={() => setPick(x.key)}>
            <span aria-hidden="true">{x.icon}</span> {x.name}
          </button>
        ))}
      </div>
      <dl className="toy-shelf" aria-live="polite">
        <div><dt>어디서</dt><dd>{s.where}</dd></div>
        <div><dt>누가 지켜 주나요</dt><dd>{s.guardOk ? '🛡️ ' : '⚠️ '}{s.guard}</dd></div>
        <div><dt>언제 꺼내요</dt><dd>{s.out}</dd></div>
        <div><dt>이자·수익</dt><dd>{s.interest}</dd></div>
      </dl>
      <p className="small" style={{ margin: 0 }}>🛡️는 예금보험공사 보호 대상이라는 뜻이에요(1인당 원금과 이자를 합쳐 1억 원까지). 상품 추천이 아니에요.</p>
    </Toy>
  )
}
