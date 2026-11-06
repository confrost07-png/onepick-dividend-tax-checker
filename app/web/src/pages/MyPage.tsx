// 마이페이지 (/mypage): 로그인한 시연용 고객의 자산관리서비스 신청 내역과 취소(모형). 내역은 이 브라우저에만 있다(applications.ts).
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { cancelApp, isPast, listApps } from '../applications'
import type { Application } from '../applications'
import { BANK, SAVED_NOTE, dateText } from '../bank'
import { usePersona } from '../persona'
import { useLoad } from '../util'

const when = (iso: string) => { const d = new Date(iso); return `${dateText(d)} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}` }

function AppCard({ a, onCancel }: { a: Application; onCancel?: () => void }) {
  const state = a.status === '취소' ? { cls: 'badge--no', txt: '취소함' } : isPast(a) ? { cls: 'badge--hold', txt: '지난 예약' } : { cls: 'badge--ok', txt: '모형 신청' }
  return (
    <li className="card my-app">
      <div className="my-app-head">
        <b>{a.typeName}</b>
        <span className={`badge ${state.cls}`}>{state.txt}</span>
      </div>
      <dl>
        <div><dt>때</dt><dd>{dateText(new Date(a.date))} {a.slot}</dd></div>
        <div><dt>곳</dt><dd>{a.where} · {a.wayName}</dd></div>
        <div><dt>점검 결과</dt><dd>{a.send ? '함께 보냄(동의함)' : '보내지 않음'}</dd></div>
        <div><dt>예약 번호(모형)</dt><dd>{a.no}</dd></div>
      </dl>
      <p className="small">신청 {when(a.createdAt)}{a.canceledAt && ` · 취소 ${when(a.canceledAt)}`}</p>
      {onCancel && <button type="button" className="btn btn--soft my-cancel" onClick={onCancel}>신청 취소</button>}
    </li>
  )
}

export default function MyPage() {
  const { id } = usePersona()
  const { data: people } = useLoad(api.personas)
  const who = people?.find(p => p.id === id)
  const [apps, setApps] = useState<Application[]>(() => (id ? listApps(id) : []))
  const [shownFor, setShownFor] = useState(id)
  const [msg, setMsg] = useState('')
  if (shownFor !== id) { setShownFor(id); setApps(id ? listApps(id) : []); setMsg('') } // 다른 고객으로 바꾸면 그 사람 내역으로

  if (!id) return (
    <div className="wrap me">
      <h1>마이페이지</h1>
      <p>로그인하면 자산관리서비스 신청 내역을 보고 취소할 수 있어요. 위쪽 메뉴의 [로그인]에서 시연용 고객을 골라 주세요.</p>
      <p className="small">로그인하지 않아도 <Link to="/wealth">자산관리서비스</Link> 신청과 다른 화면은 모두 쓸 수 있어요. 다만 신청 내역은 남지 않아요.</p>
    </div>
  )

  const cancel = (a: Application) => {
    if (!window.confirm(`${dateText(new Date(a.date))} ${a.slot} ${a.typeName} 신청을 취소할까요?`)) return
    setApps(cancelApp(id, a.no))
    setMsg(`${a.typeName} 신청을 취소했어요(모형). 실제 서비스라면 ${BANK} 앱 알림으로 취소 확인이 가요.`)
  }
  const live = apps.filter(a => a.status === '신청' && !isPast(a))
  const old = apps.filter(a => !live.includes(a))

  return (
    <div className="wrap me">
      <header className="my-head">
        <h1>마이페이지</h1>
        <p className="small">{who ? `${who.emoji} ${who.name}님` : ''} · {BANK} 로그인 상태로 가정 · 가상 인물 · <Link to="/me">내 정보 보기</Link></p>
      </header>
      {msg && <p className="notice" role="status">✓ <span>{msg}</span></p>}

      <section className="me-sec" aria-labelledby="my-live">
        <h2 id="my-live">신청 내역 <span className="small">{live.length}건</span></h2>
        {live.length
          ? <ul className="my-apps">{live.map(a => <AppCard key={a.no} a={a} onCancel={() => cancel(a)} />)}</ul>
          : <div className="card"><p style={{ marginTop: 0 }}>예정된 신청이 없어요.</p><div className="chips"><Link className="btn" to="/wealth">자산관리서비스 보기</Link><Link className="btn btn--soft" to="/consult?type=separate">세무상담 신청</Link></div></div>}
      </section>

      {old.length > 0 && (
        <section className="me-sec" aria-labelledby="my-old">
          <h2 id="my-old">지난·취소한 신청 <span className="small">{old.length}건</span></h2>
          <ul className="my-apps">{old.map(a => <AppCard key={a.no} a={a} />)}</ul>
        </section>
      )}
      <p className="small">{SAVED_NOTE}</p>
    </div>
  )
}
