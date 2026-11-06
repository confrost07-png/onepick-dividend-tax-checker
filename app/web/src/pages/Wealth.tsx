// A은행 자산관리서비스 (/wealth): 서비스 소개와 PB센터 14곳 찾기. 모형 화면이다.
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { BANK, BRANCHES, MOCK_NOTE, REGIONS } from '../bank'
import type { Region } from '../bank'
import { moaSrc } from '../util'

const SERVICES = [
  { icon: '🧾', name: '세무상담', line: '분리과세를 신청할지, 내 소득에서 무엇이 달라지는지 세무 전문가가 함께 봐요.', to: '/consult?type=separate', cta: '세무상담 신청' },
  { icon: '📮', name: '금융소득 종합과세 신고대행', line: '5월 종합소득세 확정신고를 제휴 세무법인이 대신 해요. 신고대행 수수료는 은행이 내는 것으로 가정했어요(기획안, 시연용).', to: '/consult?type=filing', cta: '신고대행 신청' },
  { icon: '🔎', name: '원픽 배당 점검', line: '내 종목이 내년에도 분리과세 대상인지, 신청하면 세금이 얼마나 달라지는지 미리 계산해요.', to: '/check', cta: '점검하기' },
  { icon: '🗂️', name: 'PB 자산관리 상담', line: '예금·투자·은퇴 준비를 PB(프라이빗 뱅커)와 한꺼번에 살펴봐요. 상품 권유는 PB 상담에서만 해요.', to: '/consult?type=general', cta: '상담 신청' },
]

const FLOW = [
  { step: '미리 보기', who: '원픽 점검', line: '대상 여부와 세액 차이를 계산해요' },
  { step: '판단하기', who: '세무상담', line: '신청할지 세무 전문가와 정해요' },
  { step: '신고하기', who: '신고대행', line: '5월 확정신고와 분리과세신청서 제출' },
]

export default function Wealth() {
  const [region, setRegion] = useState<Region | '전체'>('전체')
  const shown = region === '전체' ? BRANCHES : BRANCHES.filter(b => b.region === region)
  return (
    <div className="wrap wealth">
      <header className="wealth-hero">
        <div>
          <span className="bank-mark">{BANK}</span>
          <h1>{BANK} 자산관리서비스</h1>
          <p>배당 세금, 신고, 자산관리를 한곳에서. 원픽 점검으로 미리 보고, 필요하면 세무 전문가에게 이어 드려요.</p>
          <div className="chips">
            <Link className="btn" to="/consult?type=separate">세무상담 신청</Link>
            <a className="btn btn--soft" href="#branches">PB센터 찾기</a>
          </div>
        </div>
        <img src={moaSrc('happy')} alt="" />
      </header>
      <p className="notice">ⓘ <span>{MOCK_NOTE}</span></p>

      <section className="wealth-sec" aria-labelledby="svc">
        <h2 id="svc">이런 서비스가 있어요</h2>
        <div className="svc-grid">
          {SERVICES.map(s => (
            <Link key={s.name} to={s.to} className="svc">
              <span className="svc-icon" aria-hidden="true">{s.icon}</span>
              <b>{s.name}</b>
              <span>{s.line}</span>
              <span className="svc-go">{s.cta}</span>
            </Link>
          ))}
        </div>
      </section>

      <section className="wealth-sec" aria-labelledby="flow">
        <h2 id="flow">이렇게 이어져요</h2>
        <ol className="flow">
          {FLOW.map((f, i) => (
            <li key={f.step}><span className="flow-no">{i + 1}</span><b>{f.who}</b><span className="small">{f.step} · {f.line}</span></li>
          ))}
        </ol>
        <p className="small">기존 서비스는 신고 때(3단계)부터 도와줬어요. 원픽은 그 앞의 1단계를 채워요. 세법 해석과 신청 여부 판단은 세무 전문가가 해요.</p>
      </section>

      <section className="wealth-sec" id="branches" aria-labelledby="br">
        <h2 id="br">PB센터 찾기 <span className="tag">{BRANCHES.length}곳</span></h2>
        <div className="chips" role="group" aria-label="지역 고르기">
          {(['전체', ...REGIONS] as const).map(r => (
            <button key={r} className="chip" aria-pressed={region === r} onClick={() => setRegion(r)} style={region === r ? { background: 'var(--sea)', color: '#fff' } : undefined}>
              {r}{r !== '전체' && ` ${BRANCHES.filter(b => b.region === r).length}`}
            </button>
          ))}
        </div>
        <ul className="branch-grid">
          {shown.map(b => (
            <li key={b.id} className="branch">
              <div className="branch-top"><b>{BANK} PB센터 {b.name}점</b>{b.video && <span className="badge badge--ok">화상 가능</span>}</div>
              <span className="small">{b.area}</span>
              <span className="branch-days" aria-label="세무 전문가 상담 요일">{['월', '화', '수', '목', '금'].map(d => <i key={d} className={b.days.includes(d) ? 'on' : ''}>{d}</i>)}</span>
              <span className="small">세무 전문가 상담 요일 · 예약제</span>
              <Link className="btn btn--sm" to={`/consult?type=separate&way=visit&branch=${b.id}`}>이 지점에서 상담 신청</Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
