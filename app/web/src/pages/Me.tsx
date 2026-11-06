// 내 정보 (/me): A은행 앱에 로그인했다고 가정한 시연용 고객의 개인 페이지 (source/core/personas.py, /api/personas/{id}).
// 금융소득 합계·내 배당 점검 결과·ISA·IRP 판정은 서버가 코드로 계산한 값을 그대로 보여 준다. 추천이 아니라 계산과 조건만 보여 준다.
import { Link } from 'react-router-dom'
import { api } from '../api'
import { usePersona } from '../persona'
import { useLoad } from '../util'

const exact = (n: number) => `${n.toLocaleString('ko-KR')}원`
const pct = (p: number) => `${(p / 10).toLocaleString('ko-KR', { maximumFractionDigits: 1 })}%`
const KIND = { interest: '이자', stock: '보유 주식 배당', fund: 'ETF 분배금' } as const

export default function Me() {
  const { id } = usePersona()
  const { data: p, error } = useLoad(() => (id ? api.persona(id) : Promise.resolve(undefined)), [id])

  if (!id) return (
    <div className="wrap me">
      <h1>내 정보</h1>
      <p>로그인하면 내 소득·계좌와 점검 결과, ISA·IRP 조건을 한곳에서 볼 수 있어요. 위쪽 메뉴의 [로그인]에서 시연용 고객을 골라 주세요.</p>
      <p className="small">로그인하지 않아도 <Link to="/check">내 배당 점검</Link>과 다른 화면은 모두 쓸 수 있어요.</p>
    </div>
  )
  if (error) return <div className="wrap"><p className="error">{error}</p></div>
  if (!p) return <div className="wrap loading">불러오는 중…</div>

  const c = p.checkup
  const ii = p.isa_irp
  return (
    <div className="wrap me">
      <header className="me-hero card">
        <span className="me-face" aria-hidden>{p.emoji}</span>
        <div>
          <p className="small me-login">A은행 앱 로그인 상태로 가정 · 가상 인물</p>
          <h1>{p.name}님 <span className="small">만 {p.age}세</span></h1>
          <p className="me-job">{p.job} · {p.home}</p>
          <blockquote>“{p.quote}”</blockquote>
          <p className="small">관심사: {p.goal}</p>
        </div>
      </header>

      <section className="me-sec" aria-labelledby="me-check">
        <h2 id="me-check">내 배당 점검</h2>
        <div className="card me-check">
          <p className="me-headline">{c.headline}</p>
          {!c.no_target && c.tax.difference != null && (
            <dl className="facts">
              {c.tax.rows.map(([label, v]) => <div key={label}><dt>{label}</dt><dd>{exact(v)}</dd></div>)}
              <div className="me-diff"><dt>신청 전후 계산상 세액 차이</dt><dd>{exact(c.tax.difference)} {c.tax.direction}</dd></div>
            </dl>
          )}
          <p className="small">{c.tax.notice} 지방소득세·배당세액공제 외 세액공제·이미 낸 세금은 빼고 계산했어요. 환급액이 아니에요.</p>
          <div className="me-answers">
            <b>점검에 넣을 답</b>
            <ol>{p.answers.map((a, i) => <li key={i}>{a ?? '묻지 않음 (④에 다른 소득 있음)'}</li>)}</ol>
            <p className="small">아래 버튼을 누르면 챗봇에 이 답을 차례로 넣어 보여 드려요. 마지막 확인([맞아요])은 직접 눌러 주세요. 점검 화면에 그냥 들어가면 단계마다 '내 답' 버튼으로만 보여 드려요.</p>
          </div>
          <Link className="btn" to="/check?auto=1">이 답으로 점검 챗봇 돌려 보기</Link>
        </div>
      </section>

      <section className="me-sec" aria-labelledby="me-fin">
        <h2 id="me-fin">1년 금융소득 (세전)</h2>
        <div className="card">
          <table className="me-table">
            <tbody>
              {p.financial.map(([name, basis, v, k]) => (
                <tr key={name}><th>{name}<span className="small">{KIND[k]} · {basis}</span></th><td>{exact(v)}</td></tr>
              ))}
            </tbody>
            <tfoot><tr><th>합계</th><td>{exact(p.financial_total)}</td></tr></tfoot>
          </table>
          <p className="small">
            모두 15.4%가 원천징수됐다고 보면 실제로 들어온 돈은 {exact(p.withheld_after)}(월평균 약 {exact(Math.round(p.withheld_after / 12 / 1_000) * 1_000)})이에요.
            최종 세후소득이나 매달 고정으로 받는 돈은 아니에요.
          </p>
        </div>
      </section>

      <section className="me-sec" aria-labelledby="me-isa">
        <h2 id="me-isa">ISA · IRP — 내 조건 ({ii.basis} 기준)</h2>
        <div className="me-two">
          <div className="card">
            <h3>ISA</h3>
            {ii.isa.can_join ? (
              <>
                <p><b className="badge badge--ok">가입 가능 · {ii.isa.type}</b></p>
                <p>{ii.isa.income_year}년 {ii.basis} {exact(ii.isa.income)} 기준으로 {ii.isa.type}이에요. 계좌를 닫을 때 순이익 {exact(ii.isa.free)}까지 세금이 없어요(매년 한도가 아니에요).</p>
                <p className="small">예시: 3년 넘게 유지해 이자·배당 순이익 {exact(ii.isa.profit)}이 생기면 일반 계좌 세금 {exact(ii.isa.normal_tax)}, ISA {exact(ii.isa.isa_tax)}. 수익 예측이 아니에요.</p>
              </>
            ) : (
              <>
                <p><b className="badge badge--no">가입 제한</b></p>
                <p>{ii.isa.blocked_years.join('·')}년에 금융소득종합과세 대상이었어요. 가입 직전 3년 안에 이력이 있으면 가입할 수 없어요.</p>
              </>
            )}
            <p className="small">근거: {ii.isa.source}</p>
          </div>
          <div className="card">
            <h3>IRP</h3>
            <p><b className="badge badge--ok">공제율 {pct(ii.irp.rate_permil)}</b></p>
            <p>{ii.irp.income_year}년 {ii.basis} {exact(ii.irp.income)} 기준이에요. 본인 납입 {exact(ii.irp.irp)}이면 계산상 공제는 {exact(ii.irp.credit)}이에요.</p>
            {ii.what_if.length > 0 && (
              <table className="me-table me-table--small">
                <thead><tr><th>올해 {ii.basis}이 확정되면</th><td>공제율 · 공제</td></tr></thead>
                <tbody>{ii.what_if.map(w => <tr key={w.income}><th>{exact(w.income)}</th><td>{pct(w.rate_permil)} · {exact(w.credit)}</td></tr>)}</tbody>
              </table>
            )}
            <p className="small">확정 환급액이 아니에요. 그해 낼 세금보다 많이 돌려받지 못해요. 근거: {ii.irp.source}</p>
          </div>
        </div>
        <p className="small">{p.isa_irp_note} {ii.notice} <Link to="/isa-irp">제도별 비교에서 더 보기 →</Link></p>
      </section>

      <section className="me-sec" aria-labelledby="me-acc">
        <h2 id="me-acc">소득과 계좌</h2>
        <div className="me-two">
          <div className="card">
            <h3>소득</h3>
            <table className="me-table"><tbody>{p.income.map(([k, v]) => <tr key={k}><th>{k}</th><td>{v ? exact(v) : '없음'}</td></tr>)}</tbody></table>
            <p className="small">{p.income_note}</p>
          </div>
          <div className="card">
            <h3>계좌·제도 가입 상태</h3>
            <table className="me-table"><tbody>{p.accounts.map(([k, v]) => <tr key={k}><th>{k}</th><td className="me-left">{v}</td></tr>)}</tbody></table>
          </div>
        </div>
      </section>

      <section className="me-sec" aria-labelledby="me-tip">
        <h2 id="me-tip">놓치기 쉬운 점</h2>
        <ul className="card me-tips">{p.pitfalls.map(t => <li key={t}>{t}</li>)}</ul>
        <p className="small">다음 점검: {p.next}</p>
      </section>
      <p className="small">자료: {p.source}. 주당배당금과 판정은 원픽 DB(KIND·OpenDART) 기준이에요.</p>
    </div>
  )
}
