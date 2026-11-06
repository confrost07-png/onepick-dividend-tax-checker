// 원픽 개인정보 처리 안내(/privacy)와 이용약관 특약(/terms). A은행(가상) 앱 애드온의 모형 문서다.
import { useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { LEGAL_MOCK, PRIVACY, TERMS } from '../legal'
import type { LegalBlock, LegalDoc } from '../legal'

function Block({ b }: { b: LegalBlock }) {
  if (typeof b === 'string') return <p>{b}</p>
  if ('list' in b) return <ul>{b.list.map(x => <li key={x}>{x}</li>)}</ul>
  if ('note' in b) return <p className="legal-note">ⓘ {b.note}</p>
  return (
    <div className="legal-table">
      <table>
        <thead><tr>{b.table.head.map(h => <th key={h}>{h}</th>)}</tr></thead>
        <tbody>{b.table.rows.map(r => <tr key={r.join('|')}>{r.map((c, i) => <td key={i} data-label={b.table.head[i]}>{c}</td>)}</tr>)}</tbody>
      </table>
    </div>
  )
}

export default function Legal({ kind }: { kind: 'privacy' | 'terms' }) {
  const doc: LegalDoc = kind === 'privacy' ? PRIVACY : TERMS
  const { hash } = useLocation()
  // 다른 화면에서 '#제3조' 같은 링크로 들어오면, 화면 맨 위로 올리는 App 처리 뒤에 그 조항으로 내려간다
  useEffect(() => {
    if (!hash) return
    const t = setTimeout(() => document.getElementById(hash.slice(1))?.scrollIntoView({ block: 'start' }), 60)
    return () => clearTimeout(t)
  }, [hash, kind])
  const other = kind === 'privacy' ? { to: '/terms', label: TERMS.short } : { to: '/privacy', label: PRIVACY.short }
  return (
    <div className="wrap legal">
      <header className="legal-head">
        <span className="bank-mark">A은행 · 모형</span>
        <h1>{doc.title}</h1>
        <p className="small">{doc.version} · 시행 {doc.effective} · <Link to={other.to}>{other.label} 보기</Link></p>
        <p className="notice">ⓘ <span>{LEGAL_MOCK}</span></p>
        <p>{doc.lead}</p>
      </header>
      <div className="legal-body">
        <nav className="legal-toc" aria-label="차례">
          <b>차례</b>
          <ol>{doc.sections.map(s => <li key={s.id}><a href={`#${s.id}`}>{s.title}</a></li>)}</ol>
          <button className="btn btn--soft btn--sm" onClick={() => window.print()}>인쇄하기</button>
        </nav>
        <article>
          {doc.sections.map(s => (
            <section key={s.id} id={s.id} className="legal-sec">
              <h2>{s.title}</h2>
              {s.body.map((b, i) => <Block key={i} b={b} />)}
            </section>
          ))}
        </article>
      </div>
    </div>
  )
}
