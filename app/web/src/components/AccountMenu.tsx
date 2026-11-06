// 위쪽 메뉴의 로그인 버튼. 로그인하지 않아도 모든 화면을 쓸 수 있고, 시연용 고객으로 로그인·바꾸기·로그아웃을 여기서 한다.
import { useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { api } from '../api'
import { usePersona } from '../persona'
import { useLoad } from '../util'

export default function AccountMenu() {
  const { id, setId } = usePersona()
  const { data: people } = useLoad(api.personas)
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const { pathname } = useLocation()
  const who = people?.find(p => p.id === id)

  useEffect(() => setOpen(false), [pathname])
  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === 'Escape' : !box.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close); document.addEventListener('keydown', close)
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', close) }
  }, [open])

  return (
    <div className="acct" ref={box}>
      <button type="button" className={`me-chip${who ? ' me-chip--on' : ''}`} aria-expanded={open} aria-haspopup="menu" onClick={() => setOpen(o => !o)}>
        {who ? <><span aria-hidden>{who.emoji}</span>{who.name}님(가상)</> : '로그인'} <span aria-hidden className="acct-caret">▾</span>
      </button>
      {open && (
        <div className="acct-menu" role="menu">
          {who && <Link role="menuitem" to="/mypage">마이페이지 <span className="small">신청 내역 · 취소</span></Link>}
          {who && <Link role="menuitem" to="/me">내 정보 <span className="small">소득 · 계좌 · 점검 결과</span></Link>}
          <p className="acct-head">{who ? '다른 가상 고객으로 바꾸기' : '시연용 고객으로 로그인 (가상 인물)'}</p>
          {people?.filter(p => p.id !== id).map(p => (
            <button key={p.id} type="button" role="menuitem" onClick={() => { setId(p.id); setOpen(false) }}>
              <span aria-hidden>{p.emoji}</span> <b>{p.name}</b> <span className="small">{p.tag}</span>
            </button>
          ))}
          {who && <button type="button" role="menuitem" className="acct-out" onClick={() => { setId(null); setOpen(false) }}>로그아웃</button>}
        </div>
      )}
    </div>
  )
}
