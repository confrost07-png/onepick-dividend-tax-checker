// ISA·IRP 안내 (/isa-irp): 금융소득 2천만 원 이하 고객에게 쓸 만한 배당 절세 계좌를 계산으로만 보여 준다.
// 계산은 /api/isa-irp(core.isa_irp)가 한다. 상품 이름·가입 버튼은 넣지 않고, 가입 상담은 PB에게 잇는다.
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import type { IsaIrp as Guide } from '../api'
import { moaSrc, won } from '../util'
import RateHeat from '../components/RateHeat'

const MAN = 10_000
const permilPct = (p: number) => `${(p / 10).toLocaleString('ko-KR', { maximumFractionDigits: 1 })}%`

function ManInput({ label, value, onChange, hint }: { label: string; value: number; onChange: (v: number) => void; hint?: string }) {
  return (
    <label className="ii-field">
      <span>{label}</span>
      <span className="ii-input">
        <input type="number" inputMode="numeric" min={0} step={10} value={value / MAN}
          onChange={e => onChange(Math.max(0, Math.round(Number(e.target.value) || 0)) * MAN)} />
        <em>만 원</em>
      </span>
      {hint && <span className="small">{hint}</span>}
    </label>
  )
}

const BRACKET_KEYS = ['low', 'mid', 'high', 'biz_low', 'biz_mid', 'biz_high']
const KIND_TITLE = { wage: '근로소득만 있어요 · 총급여', business: '사업소득 등이 있어요 · 종합소득금액' } as const
const IRP_LINE = { wage: '총급여 5,500만 원', business: '종합소득금액 4,500만 원' } as const

export default function IsaIrp() {
  const [params, setParams] = useSearchParams()
  const pick = params.get('b')
  const bracket = pick && BRACKET_KEYS.includes(pick) ? pick : null
  const [profit, setProfit] = useState(300 * MAN)
  const [irp, setIrp] = useState(900 * MAN)
  const [pension, setPension] = useState(0)
  const [g, setG] = useState<Guide>()
  const [error, setError] = useState('')

  useEffect(() => {
    let alive = true
    const t = setTimeout(() => {
      api.isaIrp({ bracket, profit, irp, pension_saving: pension })
        .then(d => { if (alive) { setG(d); setError('') } }, (e: Error) => alive && setError(e.message))
    }, 200)
    return () => { alive = false; clearTimeout(t) }
  }, [bracket, profit, irp, pension])

  const choose = (key: string | null) => setParams(key ? { b: key } : {}, { replace: true, preventScrollReset: true })

  return (
    <div className="wrap wealth isa-irp">
      <header className="wealth-hero">
        <div>
          <span className="bank-mark">ISA · IRP</span>
          <h1>“그럼 소액 투자자는 쓸 게 없나요?”</h1>
          <p>금융소득이 2천만 원 이하라면 고배당 분리과세를 신청해도 세금 차이가 0원이에요. 이때는 ISA·IRP로 배당 세금이 달라질 수 있어요(계산 예시).</p>
          <div className="chips">
            <a className="btn" href="#bracket">내 구간 보기</a>
            <Link className="btn btn--soft" to="/check">먼저 내 배당 점검하기</Link>
          </div>
        </div>
        <img src={moaSrc('curious')} alt="" />
      </header>
      <p className="notice">ⓘ <span>추천이 아니라 계산이에요. 혜택과 제약을 함께 보여 드리고, 가입 상담은 PB에게 이어 드려요.</span></p>

      {error && <p className="error">{error}</p>}
      {!g ? (!error && <p className="loading">불러오는 중…</p>) : (
        <>
          <section className="wealth-sec" aria-labelledby="cmp">
            <h2 id="cmp">세 제도는 대상이 거의 겹치지 않아요</h2>
            <div className="ii-cmp" role="table" aria-label="고배당 분리과세, ISA, IRP 비교">
              {g.compare.map(c => (
                <div key={c.name} className="ii-cmp-col" role="row">
                  <b role="rowheader">{c.name}</b>
                  <p role="cell"><span className="tag">대상</span>{c.who}</p>
                  <p role="cell"><span className="tag">혜택</span>{c.benefit}</p>
                  <p role="cell"><span className="tag">제약</span>{c.limit}</p>
                </div>
              ))}
            </div>
            <p className="small">분리과세 대상(금융소득이 많은 사람)과 ISA 가입자(소액 투자자)는 대부분 겹치지 않아요. IRP 공제율은 지방소득세 포함, {g.checked} 기준 현행 제도예요.</p>
          </section>

          <section className="wealth-sec" aria-labelledby="rates" id="rates">
            <h2 id="rates">금액이 커지면 세금 가방은 얼마나 무거워질까? <span className="tag">2026년 · 지방소득세 포함</span></h2>
            <p className="ii-lead">같은 금액 구간에서 네 제도가 떼는 세율을 나란히 놓았어요. 색이 진할수록 무거워요. 줄을 누르거나 아래 막대를 움직여 보세요.</p>
            <RateHeat t={g.rate_table} />
          </section>

          <section className="wealth-sec" aria-labelledby="bracket" id="bracket">
            <h2>소득이 어느 구간인가요?</h2>
            {(['wage', 'business'] as const).map(kind => (
              <div key={kind}>
                <h3 className="ii-kind">{KIND_TITLE[kind]}</h3>
                <div className="ii-brackets" role="radiogroup" aria-label={KIND_TITLE[kind]}>
                  {g.brackets.filter(b => b.kind === kind).map(b => (
                    <button key={b.key} type="button" role="radio" aria-checked={bracket === b.key} onClick={() => choose(b.key)}>
                      <b>{b.label}</b>
                      <span>ISA {b.isa_type} {(b.isa_free / MAN).toLocaleString('ko-KR')}만 원<br />IRP 공제 {permilPct(b.irp_permil)}</span>
                    </button>
                  ))}
                  {kind === 'business' && (
                    <button type="button" role="radio" aria-checked={bracket === null} onClick={() => choose(null)}>
                      <b>잘 모르겠어요</b>
                      <span>두 공제율을 모두 계산해요</span>
                    </button>
                  )}
                </div>
              </div>
            ))}
            <p className="small">근로소득만 있으면 총급여(근로소득 원천징수영수증 21번 칸), 사업·임대·연금소득 등이 함께 있으면 종합소득금액(종합소득세 신고서)으로 봐요. ISA 유형은 가입 직전 해 소득, IRP 공제율은 돈을 넣는 해 소득으로 정해요. 여기서는 두 해 소득이 같은 구간이라고 보고 계산해요. 몰라도 그대로 진행할 수 있어요.</p>
          </section>

          <section className="wealth-sec ii-calc" aria-labelledby="calc">
            <h2 id="calc">같은 돈이라도 계좌에 따라 세금이 달라요</h2>
            <div className="ii-calc-grid">
              <div className="card ii-card">
                <h3>ISA · 이자·배당 순이익을 받으면</h3>
                <ManInput label="3년 동안 번 이자·배당 순이익" value={profit} onChange={setProfit} />
                <ul className="ii-bars">
                  {[
                    { key: 'normal', name: '일반 계좌 (15.4%)', tax: g.isa.normal },
                    { key: 'general', name: 'ISA 일반형', tax: g.isa.general },
                    { key: 'low', name: 'ISA 서민형', tax: g.isa.low_income },
                  ].map(r => {
                    const mine = g.chosen && ((r.key === 'low' && g.chosen.isa_type === '서민형') || (r.key === 'general' && g.chosen.isa_type === '일반형'))
                    return (
                      <li key={r.key} className={mine ? 'mine' : ''}>
                        <span>{r.name}{mine && <em>내 구간</em>}</span>
                        <i style={{ width: `${g.isa.normal ? Math.max(2, (r.tax / g.isa.normal) * 100) : 2}%` }} />
                        <b>{won(r.tax)}</b>
                      </li>
                    )
                  })}
                </ul>
                <p className="small">일반형은 200만 원, 서민형은 400만 원까지 세금이 없고, 넘는 부분에 9.9%를 매겨요. 계좌 안 순이익 기준이에요. 근거: {g.isa.source}</p>
                <div className="ii-limit"><b>함께 볼 제약</b> 3년은 꼭 채워야 해요 · 1년 2,000만 원, 모두 1억 원까지 · 직전 3년 안에 금융소득종합과세 대상이었다면 가입할 수 없어요</div>
              </div>

              <div className="card ii-card">
                <h3>IRP · 1년에 넣으면</h3>
                <ManInput label="IRP에 넣을 돈" value={irp} onChange={setIrp} />
                <ManInput label="연금저축에 넣을 돈" value={pension} onChange={setPension} hint="연금저축은 600만 원까지만 세고, 둘을 합쳐 900만 원까지 공제해요." />
                <ul className="ii-refund">
                  {g.irp.map(r => (
                    <li key={r.rate_permil}>
                      <span>{g.chosen ? IRP_LINE[g.chosen.kind] : '총급여 5,500만 원 · 종합소득금액 4,500만 원'} {r.rate_permil === 165 ? '이하' : '초과'} ({permilPct(r.rate_permil)})</span>
                      <b>{won(r.credit)}</b>
                    </li>
                  ))}
                </ul>
                {g.irp[0].over > 0 && <p className="small ii-over">한도를 넘은 {won(g.irp[0].over)}은 공제 셈에서 빠져요.</p>}
                <p className="small">연말정산 때 세금에서 빼 주는 금액(최대)이에요. 확정 환급액이 아니에요. 낼 세금(원천징수영수증 71번 결정세액)이 이보다 적으면 그만큼만 빼 줘요. 근거: {g.irp[0].source}</p>
                <div className="ii-limit"><b>함께 볼 제약</b> 55세 이후 연금으로 받아야 해요 · 중간에 깨면 16.5%를 내요 · 받을 때 연금소득세 3.3~5.5%</div>
              </div>
            </div>
            <p className="notice">ⓘ <span>{g.notice}</span></p>
          </section>

          <section className="wealth-sec" aria-labelledby="early">
            <h2 id="early">ISA · 3년 전에 돈이 필요하면</h2>
            <p className="ii-lead">{g.isa_early.problem} 계좌를 깨기 전에 이런 방법이 있어요.</p>
            <div className="ii-cards">
              {g.isa_early.ways.map(w => (
                <div key={w.title} className="ii-item"><span aria-hidden="true">{w.icon}</span><b>{w.title}</b><p>{w.text}</p></div>
              ))}
            </div>
            <p className="small">근거: {g.isa_early.source}</p>
          </section>

          <section className="wealth-sec" aria-labelledby="withdraw">
            <h2 id="withdraw">IRP · 중간에 꺼낼 수 있는 법정 사유</h2>
            <p className="ii-lead">IRP는 55세 전에는 원칙적으로 꺼낼 수 없지만, 아래 사유라면 중도인출을 신청할 수 있어요.</p>
            <div className="ii-cards">
              {g.irp_withdraw.reasons.map(r => (
                <div key={r.title} className="ii-item"><span aria-hidden="true">{r.icon}</span><b>{r.title}</b><p>{r.text}</p></div>
              ))}
            </div>
            <h3 className="ii-sub">이렇게 신청해요</h3>
            <ol className="flow">
              {g.irp_withdraw.steps.map((s, i) => (
                <li key={s.title}><span className="flow-no">{i + 1}</span><b>{s.title}</b><span className="small">{s.text}</span></li>
              ))}
            </ol>
            <h3 className="ii-sub">꺼낼 때 내는 세금</h3>
            <div className="ii-cards">
              {g.irp_withdraw.tax.map(t => (
                <div key={t.case} className="ii-item ii-tax"><b>{t.case}</b><span className="small">{t.examples}</span><p>{t.tax}</p></div>
              ))}
            </div>
            <p className="small">{g.irp_withdraw.note} 근거: {g.irp_withdraw.source}</p>
          </section>

          <section className="wealth-sec" aria-labelledby="facts">
            <h2 id="facts">자세한 숫자 <span className="tag">{g.checked} 현행</span></h2>
            <div className="ii-table-wrap">
              <table className="ii-table">
                <thead><tr><th scope="col">항목</th><th scope="col">ISA (개인종합자산관리계좌)</th><th scope="col">IRP (개인형 퇴직연금)</th></tr></thead>
                <tbody>{g.facts.map(f => <tr key={f.item}><th scope="row">{f.item}</th><td>{f.isa}</td><td>{f.irp}</td></tr>)}</tbody>
              </table>
            </div>
            <p className="small">{g.facts_note}</p>
            <p className="small">출처: {g.facts_source}</p>
          </section>

          <section className="wealth-sec" aria-labelledby="rcpt">
            <h2 id="rcpt">원천징수영수증, 이 칸만 보면 돼요</h2>
            <div className="ii-table-wrap">
              <table className="ii-table">
                <thead><tr><th scope="col">칸</th><th scope="col">항목</th><th scope="col">쓰는 곳</th></tr></thead>
                <tbody>{g.receipt.map(r => <tr key={r.no}><th scope="row">{r.no}번</th><td>{r.item}</td><td>{r.use}</td></tr>)}</tbody>
              </table>
            </div>
            <p className="small">영수증 2쪽에 있어요. 출처: {g.receipt_source}</p>
          </section>

          <section className="wealth-sec" aria-labelledby="why">
            <details className="basis ii-why">
              <summary id="why">왜 ‘추천’하지 않고 계산만 하나요?</summary>
              <ul>{g.why_not.map(w => <li key={w.law}><b>{w.law}</b> {w.text}</li>)}</ul>
              <p className="small">그래서 원픽은 내 구간의 혜택과 제약을 함께 계산해 보여 주고, 가입 상담은 PB에게 이어요. 법률 자문이 아니에요.</p>
            </details>
          </section>

          <section className="wealth-sec" aria-labelledby="next">
            <h2 id="next">더 알아보기</h2>
            <div className="svc-grid">
              <Link to="/consult?type=general" className="svc">
                <span className="svc-icon" aria-hidden="true">🗂️</span><b>PB 상담</b>
                <span>가입할지, 얼마나 넣을지는 PB와 함께 정해요. 상품 권유는 PB 상담에서만 해요.</span>
                <span className="svc-go">상담 신청</span>
              </Link>
              <Link to="/column/isa" className="svc">
                <span className="svc-icon" aria-hidden="true">🧺</span><b>ISA 글 읽기</b>
                <span>바구니 계좌가 어떻게 세금을 덜 떼는지, 조문과 함께 쉽게 풀었어요.</span>
                <span className="svc-go">금융 상식</span>
              </Link>
              <Link to="/column/irp" className="svc">
                <span className="svc-icon" aria-hidden="true">🏦</span><b>IRP 글 읽기</b>
                <span>넣을 때 돌려받고, 꺼낼 때 내는 세금을 순서대로 봐요.</span>
                <span className="svc-go">금융 상식</span>
              </Link>
            </div>
          </section>
        </>
      )}
    </div>
  )
}
