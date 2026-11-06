// 홈 화면(/): 회사 찾기, 2026 판정 요약, 법 토너먼트, 각 화면으로 가는 입구.
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import JudgeYear from '../components/JudgeYear'
import Search from '../components/Search'
import Tournament from '../components/Tournament'
import { moaSrc, useLoad } from '../util'

export default function Home() {
  const { data: f, error } = useLoad(api.funnel)
  const nav = useNavigate()
  const met = f ? f.ga + f.na + f.na_deficit : 0
  const fail = f ? f.fail2 + f.fail3 : 0
  const hold = f ? f.hold_missing + f.hold_zero : 0
  return (
    <div className="wrap">
      <section className="hero">
        <div>
          <h1>내 배당, 내년에도<br />분리과세 될까요?</h1>
          <p>어려운 세법은 모아가 쉬운 말로 풀어 드려요. 회사 이름만 넣어 보세요.</p>
          <Search hero placeholder="회사 이름 입력" />
          <div className="chips">
            <button className="chip chip--on-sea" onClick={() => nav('/company/005930')}>삼성전자</button>
            <button className="chip chip--on-sea" onClick={() => nav('/company/033780')}>케이티앤지</button>
          </div>
        </div>
        <img className="moa-float" src={moaSrc('base')} alt="원픽 마스코트 모아" />
      </section>

      {error && <p className="error">숫자를 불러오지 못했어요: {error}</p>}
      <div className="home-grid">
        <section className="card home-tour">
          <h2>고배당 {f?.total ?? 638}곳의 법 토너먼트</h2>
          <p className="small" style={{ margin: '0 0 14px' }}>동전 하나가 회사 하나예요. 법이 정한 문 세 개를 지나야 분리과세 대상이 돼요.</p>
          {f ? <Tournament funnel={f} compact /> : <div className="loading">불러오는 중…</div>}
        </section>
        <section className="card verdict" aria-label="2026 판정">
          <span className="tag">2026 판정 · 현재 해석 기준</span>
          <p style={{ margin: '12px 0 0', fontWeight: 800 }}>{f?.total ?? '…'}곳 중</p>
          <b className="big-n num">{f ? met : '…'}</b><span className="round" style={{ fontSize: 28 }}> 곳 통과</span>
          {f && <div className="stack" aria-hidden="true">
            {[met, fail, hold].map((n, i) => <span key={i} style={{ width: `${n / f.total * 100}%` }} />)}
          </div>}
          <ul className="legend">
            <li><i style={{ background: 'var(--sea)' }} />충족<em>{f ? met : ''}</em></li>
            <li><i style={{ background: 'var(--no)' }} />미충족<em>{f ? fail : ''}</em></li>
            <li><i style={{ background: '#C9CFD9' }} />판정 보류<em>{f ? hold : ''}</em></li>
          </ul>
          <p className="small" style={{ margin: '14px 0 0' }}>판정 보류는 자료를 확인하는 중이거나, 해석이 아직 정해지지 않은 회사예요.</p>
          <JudgeYear />
        </section>
      </div>

      <div className="doors">
        <Link className="door" to="/check">
          <h3>내 배당 점검하기</h3>
          <p>보유 종목과 소득을 대화로 답하면, 분리과세를 신청했을 때 세금이 얼마나 달라지는지 계산해요.</p>
          <span className="go">점검 시작 →</span>
          <img src={moaSrc('base')} alt="" />
        </Link>
        <Link className="door" to="/analysis">
          <h3>데이터 이야기 보기</h3>
          <p>올해 붙은 회사 절반이 다음 해엔 떨어졌어요. 숫자로 따라가 보세요.</p>
          <span className="go">이야기 보기 →</span>
          <img src={moaSrc('curious')} alt="" />
        </Link>
        <Link className="door door--column" to="/column">
          <h3>모아의 금융 상식 칼럼</h3>
          <p>배당은 피자 나눠 먹기, 초과수익률은 달리기 시합. 어려운 금융 용어를 그림으로 만져 보며 알아봐요.</p>
          <span className="go">칼럼 읽기 →</span>
          <img src={moaSrc('happy')} alt="" />
        </Link>
      </div>
    </div>
  )
}
