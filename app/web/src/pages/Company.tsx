// 회사 보기 (/company/:code): 이 회사 동전이 법 토너먼트에서 지난 길과 2027년 최소 필요 배당.
// 회사별 공시 뒤 주가 반응은 보여 주지 않는다(팀 원칙).
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api'
import type { Stock } from '../api'
import JudgeYear from '../components/JudgeYear'
import { badgeClass, moaSrc, moodOf, pct, useLoad, won } from '../util'

type StepState = 'pass' | 'fail' | 'hold' | 'skip' | 'goal'

function rounds(s: Stock): { state: StepState; title: string; text: string; why?: ReactNode }[] {
  const first = s.reasons[0] ?? ''
  const r1: StepState = s.status === '판정 보류' && !first.startsWith('전전') ? 'hold' : 'pass'
  const r2: StepState = r1 !== 'pass' ? 'skip' : first.startsWith('제2호') ? 'fail' : 'pass'
  const r3: StepState = r2 !== 'pass' ? 'skip' : s.status === '충족' ? 'pass' : s.status === '판정 보류' ? 'hold' : 'fail'
  // 금액·비율은 숫자 중간에서 줄이 바뀌지 않게 nb(줄바꿈 막기)로 묶는다.
  const payout = s.deemed_payout != null ? `적자라 배당성향 ${s.deemed_payout}%로 봐요` : `배당성향 ${pct(s.payout_pct)}`
  const end: StepState = s.status === '충족' ? 'goal' : s.status === '미충족' ? 'fail' : 'hold'
  return [
    { state: r1, title: '1라운드', text: r1 === 'hold' ? '판정 숫자를 확인하는 중이에요' : '판정 숫자가 다 있어요', why: r1 === 'hold' ? first : undefined },
    { state: r2, title: '2라운드 · 제2호', text: r2 === 'fail' ? '배당이 2024년보다 줄었어요' : '배당이 줄지 않았는지',
      why: s.b2024 != null && s.b2025 != null && r2 !== 'skip' ? <>배당소득 <span className="nb">{won(s.b2024)} →</span> <span className="nb">{won(s.b2025)} ({pct(s.b_growth_pct, true)})</span></> : undefined },
    { state: r3, title: s.route ? `3라운드 · ${s.route === '가목' ? '가목 언덕' : '나목 계단'}` : '3라운드 · 제3호',
      text: s.route === '가목' ? '배당성향 40% 이상' : s.route === '나목' ? '25% 이상 + 배당 10%↑' : r3 === 'skip' ? '가목 또는 나목' : first,
      why: r3 !== 'skip' ? <><span className="nb">{payout}</span> · <span className="nb">이익배당 {pct(s.d_growth_pct, true)}</span></> : undefined },
    { state: end, title: s.status === '충족' ? '2026 통과' : s.status === '미충족' ? '이번엔 탈락' : '판정 보류', text: s.status === '충족' ? '2026 사업연도 배당이 분리과세 대상' : first },
  ]
}

const MARK: Record<StepState, string> = { pass: '✓', fail: '✕', hold: '?', skip: '–', goal: '★' }

export default function Company() {
  const { code = '' } = useParams()
  const { data: s, error } = useLoad(() => api.company(code), [code])
  const [copied, setCopied] = useState(false)
  const [fill, setFill] = useState(0)
  useEffect(() => { setFill(0); const t = setTimeout(() => setFill(1), 80); return () => clearTimeout(t) }, [s])

  if (error) return <div className="wrap"><p className="error">{error}</p></div>
  if (!s) return <div className="wrap loading">불러오는 중…</div>

  const mood = moodOf(s.status)
  const have = s.d2025 ?? 0, need = s.need_2027
  const max = need != null ? Math.max(have, need) : have
  const more = need != null && need > have
  const hello = s.status === '충족' ? `${s.name} 동전은 세 라운드를 모두 지나 ${s.route === '가목' ? '가목 언덕' : '나목 계단'}에 올라섰어요!`
    : s.status === '미충족' ? `${s.name} 동전은 이번 토너먼트에서 멈췄어요. 아래에서 어느 문이었는지 보세요.`
      : `${s.name} 동전은 대기석에 있어요. 확인이 끝나면 다시 달려요.`
  const copy = () => navigator.clipboard?.writeText(location.href).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500) })

  return (
    <div className="wrap">
      <div className="co-head">
        <h1>{s.name}</h1><span className="small">{s.code}</span>
        <span className={`badge ${badgeClass(s.status)}`}>{s.status}{s.route ? ` · ${s.route}` : ''}</span>
        <span className="tag">{s.status === '판정 보류' ? '판정 보류' : '현재 해석 기준'}</span>
        <button className="btn btn--soft btn--sm" style={{ marginLeft: 'auto' }} onClick={copy}>주소 복사</button>
      </div>

      <section className="card" aria-label="법 토너먼트에서 지난 길">
        <div className="moa-say" style={{ marginBottom: 22 }}><img className="moa-pop" src={moaSrc(mood)} alt="" key={s.code} /><p>{hello}</p></div>
        <ol className="path" style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {rounds(s).map(r => (
            <li key={r.title} className={`step ${r.state}`}>
              <div className="dot" aria-hidden="true">{MARK[r.state]}</div>
              <h4>{r.title}</h4><p>{r.text}</p>
              {r.why && <span className="why">{r.why}</span>}
            </li>
          ))}
        </ol>
        <JudgeYear />
      </section>

      <section className="card" style={{ marginTop: 20 }} aria-label="2027 사업연도 배당">
        <span className="tag">다음 판정 · 2027 사업연도 배당</span>
        {need == null ? (
          <p className="big">2027년 최소 필요 배당은 <em>계산하지 않았어요</em></p>
        ) : (
          <p className="big">{more ? <>2027년엔 2025년보다 <em>{won(need - have)}</em> 더 줘야 해요</> : '2025년만큼만 줘도 2027년 요건을 넘어요'}</p>
        )}
        {need != null && (
          <div className="gauge" role="img" aria-label={`2025 배당 ${won(have)}, 2027 최소 필요 ${won(need)}`}>
            <div className="gauge__track"><div className="gauge__fill" style={{ width: `${fill * Math.min(100, have / max * 100)}%` }} /></div>
            <div className="gauge__mark" style={{ left: `calc(${Math.min(100, need / max * 100)}% - 2px)` }}><span>2027 최소</span></div>
          </div>
        )}
        <dl className="facts">
          <div><dt>2025 배당</dt><dd>{s.d2025 != null ? won(s.d2025) : '–'}</dd></div>
          <div><dt>2027 최소 필요</dt><dd>{need != null ? `${won(need)} (${pct(s.ratio_to_2025_pct)})` : s.need_status ?? '–'}</dd></div>
          <div><dt>2025 배당성향</dt><dd>{pct(s.payout_pct)}</dd></div>
        </dl>
        <p className="small" style={{ margin: '12px 0 0' }}>2026년 순이익이 2025년과 같다고 가정했어요. 결과는 2027년 2~3월 배당 결정 공시에서 확인할 수 있어요.</p>
        {s.sources.length > 0 && <div className="outlinks">{s.sources.map(l => <a key={l.url + l.label} className="chip" href={l.url} target="_blank" rel="noreferrer">{l.label} ↗</a>)}</div>}
      </section>
      {copied && <div className="toast" role="status">주소를 복사했어요</div>}
    </div>
  )
}
