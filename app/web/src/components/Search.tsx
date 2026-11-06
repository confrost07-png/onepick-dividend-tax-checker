// 회사 찾기: 글자를 치는 동안 후보가 뜬다(↑↓·Enter·Esc). 어디서든 '/' 키로 연다.
import { useEffect, useId, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'

export default function Search({ hero = false, slashKey = false, placeholder = '회사 찾기' }: { hero?: boolean; slashKey?: boolean; placeholder?: string }) {
  const [q, setQ] = useState('')
  const [items, setItems] = useState<{ name: string; code: string }[]>([])
  const [open, setOpen] = useState(false)
  const [sel, setSel] = useState(0)
  const input = useRef<HTMLInputElement>(null)
  const nav = useNavigate()
  const listId = useId()

  useEffect(() => {
    if (!q.trim()) { setItems([]); return }
    const t = setTimeout(() => api.search(q).then(r => { setItems(r); setSel(0) }).catch(() => setItems([])), 120)
    return () => clearTimeout(t)
  }, [q])

  useEffect(() => {
    if (!slashKey) return
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName
      if (e.key === '/' && tag !== 'INPUT' && tag !== 'TEXTAREA') { e.preventDefault(); input.current?.focus() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [slashKey])

  const go = (code: string) => { setOpen(false); setQ(''); input.current?.blur(); nav(`/company/${code}`) }
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setSel(s => Math.min(s + 1, items.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setSel(s => Math.max(s - 1, 0)) }
    else if (e.key === 'Enter' && items[sel]) { e.preventDefault(); go(items[sel].code) }
    else if (e.key === 'Escape') { setOpen(false); input.current?.blur() }
  }

  return (
    <div className={`find${hero ? ' find--hero' : ''}`}>
      <label className="sr" htmlFor={`${listId}-in`}>회사 이름이나 종목코드</label>
      <input
        id={`${listId}-in`} ref={input} value={q} placeholder={placeholder} autoComplete="off"
        role="combobox" aria-expanded={open && !!q} aria-controls={listId}
        aria-activedescendant={items[sel] ? `${listId}-${sel}` : undefined}
        onChange={e => { setQ(e.target.value); setOpen(true) }} onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)} onKeyDown={onKeyDown}
      />
      {slashKey && !q && <kbd>/</kbd>}
      {open && q.trim() && (
        <ul id={listId} role="listbox">
          {items.length === 0 && <li className="empty">조회 결과가 없어요. 기업명 표기를 확인해 주세요. 고배당기업 조회 대상 638곳 안에서만 찾아요.</li>}
          {items.map((it, i) => (
            <li key={it.code} id={`${listId}-${i}`} role="option" aria-selected={i === sel}
              onMouseEnter={() => setSel(i)} onMouseDown={e => { e.preventDefault(); go(it.code) }}>
              {it.name}<small>{it.code}</small>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
