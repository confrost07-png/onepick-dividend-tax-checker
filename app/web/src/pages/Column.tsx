// 모아의 금융 상식 칼럼 (/column, /column/:id): 어려운 금융 용어를 쉬운 말과 그림 도구로 풀고, 조문 원문은 접어 둔다.
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import type { DictTerm, Passage } from '../api'
import { COLUMN_NOTE, EPISODES, GLOSSARY, READ_ORDER, START_HERE, THEMES, UNITS, themeOf, themeUnits } from '../column'
import type { Block, Source, Toy } from '../column'
import { ColumnIcon } from '../components/columnIcons'
import { Account, Balance, Basket, Brakes, Capital, Coins, DelistPath, Deposit, DisclosureSort, DivCalendar, EldInterest, ElsPath, EtfEtn, FinIncome, Fx, Gates, GrossUp, IncomeSort, IndexMaker, Ipo, IsaBox, Ledger, Meeting, Merger, Payback, PensionCredit, Pizza, Race, RateMachine, RecordDay, Savings, Shelf, Splitter, Spread, StockBond, TaxFlow, TaxHelper, TaxStairs, Votes, Wallet, Waterfall, WealthMap, Withhold, Yields } from '../components/columnToys'
import { moaSrc, useLoad } from '../util'

const unitOf = (id: string) => UNITS.find(u => u.ids.includes(id))!

const SRC_CLASS: Record<Source, string> = { '조문': 'src--law', '팀 해석': 'src--team', '데이터': 'src--data', '쉬운 설명': 'src--easy' }
const TOYS: Record<Toy, () => ReactNode> = {
  pizza: Pizza, stairs: TaxStairs, gates: Gates, balance: Balance, wallet: Wallet, race: Race, lineup: Spread, coins: Coins,
  stockbond: StockBond, votes: Votes, taxhelper: TaxHelper, wealth: WealthMap,
  fincome: FinIncome, withhold: Withhold, kinds: IncomeSort, grossup: GrossUp, savings: Savings, fx: Fx, account: Account, basket: Basket,
  yields: Yields, divcal: DivCalendar, recordday: RecordDay, payback: Payback, taxflow: TaxFlow,
  index: IndexMaker, knockin: ElsPath, eld: EldInterest, etn: EtfEtn, meeting: Meeting, splitter: Splitter, merger: Merger,
  ipo: Ipo, delistpath: DelistPath, waterfall: Waterfall, capital: Capital,
  ledger: Ledger, disclosure: DisclosureSort, ratemachine: RateMachine, brakes: Brakes,
  isabox: IsaBox, pension: PensionCredit, deposit: Deposit, shelf: Shelf,
}

const TOY_NAMES: Record<Toy, string> = {
  pizza: '피자 나눠 먹기', stairs: '세율 계단', gates: '문 세 개 열기', balance: '빚 저울', wallet: '용돈 지갑', race: '실제 공시 달리기',
  lineup: '실제 사례 점 찍기', coins: '동전 던지기', stockbond: '가게 주인과 빌려준 사람', votes: '100주짜리 회사', taxhelper: '누가 무엇을 하나',
  wealth: '배당 받는 1년', fincome: '2천만 원 선', withhold: '배당 받는 날 통장', kinds: '소득 주머니', grossup: '두 번 내지 않게', savings: '복리 저금통',
  fx: '환율 다이얼', account: '나라 가계부', basket: '장바구니', yields: '수익률 vs 성향', divcal: '배당 달력', recordday: '언제 사야 받을까',
  payback: '주주환원 바구니', taxflow: '세금 계산 길',
  index: '지수 만들기', knockin: 'ELS 길 따라가기', eld: 'ELD 저금통 나누기', etn: 'ETF와 ETN 견주기', meeting: '주주총회 표 세기',
  splitter: '피자 다시 자르기', merger: '두 가게 합치기', ipo: '공모주 나눠 받기', delistpath: '상장폐지 가는 길', waterfall: '남은 돈 나눠 갖기 순서', capital: '주식 늘리고 줄이기',
  ledger: '가게 장부 써 보기', disclosure: '이 소식은 어느 공시?', ratemachine: '기준금리 손잡이', brakes: '시장 브레이크 걸기',
  isabox: 'ISA 바구니에 담아 보기', pension: '연금 세액공제 계산', deposit: '예금 vs 적금 이자 견주기', shelf: '돈 맡길 곳 견주기',
}
const toyOf = (id: string): Toy | undefined => {
  const b = EPISODES.find(e => e.id === id)?.blocks.find(x => x.t === 'toy')
  return b && b.t === 'toy' ? b.toy : undefined
}

// 읽은 칸: 이 브라우저에만 기억한다(다른 사람과 나누지 않음)
const READ_KEY = 'onepick-column-read'
function readSet(): Set<string> {
  try { return new Set(JSON.parse(localStorage.getItem(READ_KEY) ?? '[]')) } catch { return new Set() }
}
function markRead(id: string) {
  try { const s = readSet(); s.add(id); localStorage.setItem(READ_KEY, JSON.stringify([...s])) } catch { /* 저장이 막혀 있으면 기억하지 않는다 */ }
}

/** {이름} 자리에 넣을 API 값 (판정 흐름·분석 결과) */
function useFacts() {
  const f = useLoad(api.funnel).data
  const a = useLoad(api.analysis).data
  const up = a?.event.curves['주당배당금 증가']
  const end = up?.[up.length - 1]
  const facts: Record<string, string | undefined> = {
    fail2: f?.fail2.toLocaleString('ko-KR'), na_deficit: f?.na_deficit.toLocaleString('ko-KR'), hold_missing: f?.hold_missing.toLocaleString('ko-KR'),
    p24: a?.payout.find(r => r[0] === 24)?.[1].toLocaleString('ko-KR'), p25: a?.payout.find(r => r[0] === 25)?.[1].toLocaleString('ko-KR'),
    cap_median: a?.capacity.median?.toString(), cap_low: a?.capacity.bins[0]?.[1].toLocaleString('ko-KR'),
    policy_filings: a?.trust.policy_filings.toLocaleString('ko-KR'),
    car_up: end ? `${end[2] > 0 ? '+' : ''}${end[2].toFixed(2)}` : undefined, car_n: end?.[1].toLocaleString('ko-KR'),
  }
  return facts
}

/** 글 안의 {{용어}}는 누르면 뜻이 열리는 단어로, {이름}은 API 값으로 바꾼다 */
function Rich({ text, facts }: { text: string; facts: Record<string, string | undefined> }) {
  const parts = text.split(/(\{\{[^}]+\}\}|\{\w+\})/g)
  return <>{parts.map((p, i) => {
    const term = p.match(/^\{\{(.+)\}\}$/)
    if (term) return <Term key={i} word={term[1]} />
    const fact = p.match(/^\{(\w+)\}$/)
    if (fact) return <b key={i}>{facts[fact[1]] ?? '…'}</b>
    return <span key={i}>{p}</span>
  })}</>
}

function Term({ word }: { word: string }) {
  const [open, setOpen] = useState(false)
  useEffect(() => { // 화면을 움직이면 뜻 풀이를 닫는다
    if (!open) return
    const close = () => setOpen(false)
    window.addEventListener('scroll', close, { passive: true, once: true })
    return () => window.removeEventListener('scroll', close)
  }, [open])
  const g = GLOSSARY[word]
  if (!g) return <>{word}</>
  return (
    <span className="term-wrap">
      <button className="term" aria-expanded={open} onClick={() => setOpen(!open)} onBlur={() => setOpen(false)}>{word}</button>
      {open && <span className="term-pop" role="tooltip"><b>{word}</b> {g.easy}{g.like && <em> 비유하면: {g.like}</em>}</span>}
    </span>
  )
}

export default function Column() {
  const { id } = useParams()
  const facts = useFacts()
  const ep = EPISODES.find(e => e.id === id)
  if (id && !ep) return <div className="wrap loading">찾는 글이 없어요. <Link to="/column">칼럼 목록으로</Link></div>
  if (ep) return <EpisodeView key={ep.id} id={ep.id} facts={facts} />
  return <ColumnIndex facts={facts} />
}

const plainHook = (hook: string, facts: Record<string, string | undefined>) =>
  hook.replace(/\{\{([^}]+)\}\}/g, '$1').replace(/\{(\w+)\}/g, (_, k: string) => facts[k] ?? '…')

function ColumnIndex({ facts }: { facts: Record<string, string | undefined> }) {
  const [read, setRead] = useState<Set<string>>(readSet)
  const [params, setParams] = useSearchParams()
  const [q, setQ] = useState('')
  const tab = params.get('t') ?? THEMES[0].key
  const glQ = params.get('q') ?? '' // 용어 사전 탭의 찾는 말(주소에 남겨 칼럼 첫 화면 검색에서 바로 열 수 있게)
  const theme = THEMES.find(t => t.key === tab)
  const nextId = READ_ORDER.find(x => !read.has(x)) ?? READ_ORDER[0]
  const nextEp = EPISODES.find(e => e.id === nextId)!
  const word = q.trim()
  const found = word ? EPISODES.filter(e => [e.title, plainHook(e.hook, facts), ...e.terms].some(s => s.includes(word))) : []
  const row = (id: string) => <EpRow key={id} id={id} facts={facts} isRead={read.has(id)} isNext={id === nextId} />
  return (
    <div className="wrap col-index">
      <header className="col-hero">
        <div>
          <h1>모아의 금융 상식 칼럼</h1>
          <p>주식과 배당부터 세금, 경제 이야기까지 {EPISODES.length}편이에요. 팀원들이 실제로 궁금해한 질문 66개를 풀었고, 글마다 손으로 움직여 보는 그림이 있어요.</p>
          <input className="col-search" type="search" value={q} onChange={e => setQ(e.target.value)} placeholder="제목·용어로 찾기 (예: 배당락)" aria-label="칼럼 찾기" />
        </div>
        <div className="trail-card">
          <div className="trail-head"><img src={moaSrc('happy')} alt="" /><span>모아와 함께 <b>{read.size}</b> / {EPISODES.length}편 읽었어요</span></div>
          <ul className="theme-bars" aria-label="묶음별로 읽은 편수">
            {THEMES.map(t => {
              const ids = themeUnits(t).flatMap(u => u.ids), done = ids.filter(x => read.has(x)).length
              return (
                <li key={t.key} style={{ ['--u' as string]: t.color }}>
                  <span>{t.name}</span><b>{done} / {ids.length}</b>
                  <i aria-hidden="true"><i style={{ width: `${(done / ids.length) * 100}%` }} /></i>
                </li>
              )
            })}
          </ul>
          <Link to={`/column/${nextId}`} className="btn">{read.size ? '이어서 읽기' : '첫 편부터 읽기'}: {nextEp.no}. {nextEp.title}</Link>
          {read.size > 0 && <button className="small trail-reset" onClick={() => { try { localStorage.removeItem(READ_KEY) } catch { /* 무시 */ } setRead(new Set()) }}>읽은 기록 지우기</button>}
        </div>
      </header>

      {word ? (
        <section className="col-list" aria-label="찾은 글">
          <h2 className="col-list-h">‘{word}’ 찾은 글 {found.length}편</h2>
          {found.length ? <ol className="ep-rows">{found.map(e => row(e.id))}</ol> : <p className="small">맞는 글이 없어요. 다른 말로 찾거나 아래 묶음에서 골라 보세요.</p>}
          <button className="btn btn--soft gl-jump" onClick={() => { setQ(''); setParams({ t: 'glossary', q: word }, { replace: true }) }}>
            📖 용어 사전에서 ‘{word}’ 찾기
          </button>
        </section>
      ) : (
        <>
          <section className="col-start" aria-labelledby="col-start-h">
            <h2 id="col-start-h">처음이라면 이 {START_HERE.length}편</h2>
            <ol className="start-cards">
              {START_HERE.map(id => {
                const e = EPISODES.find(x => x.id === id)!, u = unitOf(id)
                return (
                  <li key={id}>
                    <Link to={`/column/${id}`} className={`start-card ${read.has(id) ? 'read' : ''}`} style={{ ['--u' as string]: u.color, ['--ut' as string]: u.tint }}>
                      <ColumnIcon id={id} size={44} />
                      <span>{e.title}</span>
                      {read.has(id) && <span className="paw" aria-label="읽음">🐾</span>}
                    </Link>
                  </li>
                )
              })}
            </ol>
          </section>

          <div className="theme-tabs" role="tablist" aria-label="묶음">
            {THEMES.map(t => (
              <button key={t.key} role="tab" aria-selected={tab === t.key} style={{ ['--u' as string]: t.color, ['--ut' as string]: t.tint }}
                onClick={() => setParams({ t: t.key }, { replace: true })}>{t.name}</button>
            ))}
            <button role="tab" aria-selected={tab === 'glossary'} onClick={() => setParams({ t: 'glossary' }, { replace: true })}>📖 용어 사전</button>
          </div>

          {theme ? (
            <section className="col-list" role="tabpanel" style={{ ['--u' as string]: theme.color, ['--ut' as string]: theme.tint }} aria-label={theme.name}>
              <p className="col-list-line">{theme.line}</p>
              {themeUnits(theme).map(u => (
                <div key={u.no} className="unit-block" style={{ ['--u' as string]: u.color, ['--ut' as string]: u.tint }}>
                  <h3>{u.name} <span>{u.ids.filter(x => read.has(x)).length} / {u.ids.length}</span></h3>
                  <ol className="ep-rows">{u.ids.map(row)}</ol>
                </div>
              ))}
            </section>
          ) : <Glossary q={glQ} setQ={q => setParams({ t: 'glossary', ...(q ? { q } : {}) }, { replace: true })} />}
        </>
      )}
      <p className="small col-note">{COLUMN_NOTE}</p>
    </div>
  )
}

/** 목록 한 줄: 그림 · 번호와 제목 · 한 줄 소개 · 읽음 */
function EpRow({ id, facts, isRead, isNext }: { id: string; facts: Record<string, string | undefined>; isRead: boolean; isNext: boolean }) {
  const e = EPISODES.find(x => x.id === id)!, u = unitOf(id), toy = toyOf(id)
  return (
    <li>
      <Link to={`/column/${id}`} className={`ep-row ${isRead ? 'read' : ''} ${isNext ? 'next' : ''}`} style={{ ['--u' as string]: u.color, ['--ut' as string]: u.tint }}>
        <span className="ep-row-art"><ColumnIcon id={id} size={40} /></span>
        <span className="ep-row-body">
          <b><span className="ep-row-no">{e.no}</span>{e.title}</b>
          <span className="ep-row-hook">{plainHook(e.hook, facts)}</span>
          {toy && <span className="ep-row-toy">🖐 {TOY_NAMES[toy]}</span>}
        </span>
        <span className="ep-row-state">{isRead ? '🐾 읽음' : isNext ? '다음 차례' : ''}</span>
      </Link>
    </li>
  )
}

const CHOSUNG = 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ'
const initial = (w: string) => { const c = w.charCodeAt(0) - 0xac00; return c >= 0 && c < 11172 ? CHOSUNG[Math.floor(c / 588)].replace('ㄲ', 'ㄱ').replace('ㄸ', 'ㄷ').replace('ㅃ', 'ㅂ').replace('ㅆ', 'ㅅ').replace('ㅉ', 'ㅈ') : 'A–Z' }

// 용어 사전 탭: 모아 칼럼 사전 + 금융위원회 금융용어사전 + 원픽 보충 용어를 한 목록으로. 이름·별칭이 맞는 것을 먼저, 그다음 풀이 글에 든 것
type Src = 'moa' | 'fsc' | 'onepick'
interface GlTerm { term: string; aliases: string[]; text: string; like?: string; src: Src; source_name?: string; source_url?: string; ep?: (typeof EPISODES)[number] }
const SRC_NAME: Record<Src, string> = { moa: '모아 칼럼', fsc: '금융위원회', onepick: '원픽 보충' }
const norm = (s: string) => s.toLowerCase().replace(/[\s·ㆍ,\-()'"?]/g, '')

function glossaryTerms(extra: DictTerm[]): GlTerm[] {
  const moa: GlTerm[] = Object.entries(GLOSSARY).map(([w, d]) => ({
    term: w, aliases: [], text: d.easy, like: d.like, src: 'moa', ep: EPISODES.find(e => e.terms.includes(w)),
  }))
  const seen = new Set(moa.map(t => norm(t.term)))
  // 칼럼 사전에 이미 있는 용어는 칼럼 풀이만 보인다(챗봇과 같은 순서)
  const more: GlTerm[] = extra.filter(t => !seen.has(norm(t.term.replace(/\(.*?\)/g, '')))).map(t => ({
    term: t.term, aliases: t.aliases, text: t.definition, src: t.kind, source_name: t.source_name, source_url: t.source_url,
  }))
  return [...moa, ...more].sort((a, b) => a.term.localeCompare(b.term, 'ko'))
}

/** 찾는 말에 맞는 용어: 0 이름이 같음 · 1 이름·별칭에 들어 있음 · 2 풀이 글에 들어 있음 */
function rank(t: GlTerm, q: string): number | null {
  const names = [t.term, t.term.replace(/\(.*?\)/g, ''), ...t.aliases].map(norm)
  if (names.includes(q)) return 0
  if (names.some(n => n.includes(q))) return 1
  return norm(t.text + (t.like ?? '')).includes(q) ? 2 : null
}

function Glossary({ q, setQ }: { q: string; setQ: (q: string) => void }) {
  const extra = useLoad(() => api.terms())
  const [src, setSrc] = useState<Src | 'all'>('all')
  const all = glossaryTerms(extra.data?.terms ?? [])
  const pool = src === 'all' ? all : all.filter(t => t.src === src)
  const key = norm(q)
  const found = key ? pool.map(t => ({ t, r: rank(t, key) })).filter(x => x.r !== null).sort((a, b) => a.r! - b.r!).map(x => x.t) : []
  const count = (s: Src) => all.filter(t => t.src === s).length
  const groups = [...new Set(pool.map(t => initial(t.term)))]
  return (
    <section className="glossary" id="glossary" aria-label="용어 사전">
      <h2>모아의 용어 사전</h2>
      <p className="gl-lead">모아 칼럼 풀이 {count('moa')}개에 금융위원회 금융용어사전 {count('fsc')}개, 원픽 보충 용어 {count('onepick')}개를 함께 찾아요.</p>
      <div className="gl-tools">
        <input className="col-search gl-search" type="search" value={q} onChange={e => setQ(e.target.value)}
          placeholder="용어나 뜻으로 찾기 (예: 블록딜, 금리)" aria-label="용어 사전에서 찾기" />
        <div className="gl-srcs" role="group" aria-label="사전 고르기">
          {(['all', 'moa', 'fsc', 'onepick'] as const).map(s => (
            <button key={s} aria-pressed={src === s} onClick={() => setSrc(s)}>
              {s === 'all' ? `전체 ${all.length}` : `${SRC_NAME[s]} ${count(s)}`}
            </button>
          ))}
        </div>
      </div>
      {extra.error && <p className="small">금융위원회·원픽 보충 사전을 불러오지 못해 모아 칼럼 풀이만 보여요.</p>}
      {key ? (
        <div className="gl-results" aria-live="polite">
          <p className="small">'{q.trim()}' {found.length ? `${found.length}개` : '— 맞는 용어가 없어요. 다른 말로 찾거나 사전을 [전체]로 바꿔 보세요.'}</p>
          <dl>{found.map(t => <GlItem key={t.src + t.term} t={t} notice={extra.data?.notice} />)}</dl>
        </div>
      ) : (
        <>
          <nav className="gl-index" aria-label="첫 글자로 찾기">{groups.map(g => <a key={g} href={`#gl-${g}`}>{g}</a>)}</nav>
          {groups.map(g => (
            <div key={g} className="gl-group" id={`gl-${g}`}>
              <span className="gl-letter">{g}</span>
              <dl>{pool.filter(t => initial(t.term) === g).map(t => <GlItem key={t.src + t.term} t={t} notice={extra.data?.notice} />)}</dl>
            </div>
          ))}
        </>
      )}
    </section>
  )
}

function GlItem({ t, notice }: { t: GlTerm; notice?: Record<'fsc' | 'onepick', string> }) {
  return (
    <div>
      <dt>{t.term} {t.src !== 'moa' && <span className={`gl-src ${t.src}`}>{SRC_NAME[t.src]}</span>}</dt>
      <dd>
        {t.text}{t.like && <em>비유하면: {t.like}</em>}
        {t.ep && <Link to={`/column/${t.ep.id}`} className="gl-ep">{t.ep.no}. {t.ep.title}</Link>}
        {t.source_url && <a href={t.source_url} target="_blank" rel="noreferrer" className="gl-ep" title={notice?.[t.src as 'fsc' | 'onepick']}>출처: {t.source_name}</a>}
      </dd>
    </div>
  )
}

function EpisodeView({ id, facts }: { id: string; facts: Record<string, string | undefined> }) {
  const ep = EPISODES.find(e => e.id === id)!
  const u = unitOf(id), k = u.ids.indexOf(id), theme = themeOf(id)
  const nextId = READ_ORDER[READ_ORDER.indexOf(id) + 1], next = EPISODES.find(e => e.id === nextId)
  const [progress, setProgress] = useState(0)
  useEffect(() => { document.title = `${ep.title} · 원픽 금융 상식 칼럼` }, [ep])
  useEffect(() => {
    const on = () => { const h = document.documentElement.scrollHeight - innerHeight; setProgress(h > 0 ? Math.min(1, scrollY / h) : 0) }
    on(); addEventListener('scroll', on, { passive: true })
    return () => removeEventListener('scroll', on)
  }, [])
  useEffect(() => { if (progress > 0.85) markRead(id) }, [progress, id])
  return (
    <div className="col-ep" style={{ ['--u' as string]: u.color, ['--ut' as string]: u.tint }}>
      <div className="read-bar" style={{ transform: `scaleX(${progress})` }} aria-hidden="true" />
      <header className="ep-hero">
        <div className="wrap ep-hero-in">
          <div>
            <nav className="ep-crumb" aria-label="위치">
              <Link to="/column">금융 상식 칼럼</Link>
              <Link to={`/column?t=${theme.key}`}>{theme.name}</Link>
              <span>{u.name}</span>
              <span className="ep-steps" aria-label={`${u.ids.length}칸 중 ${k + 1}번째`}>{u.ids.map((x, i) => <i key={x} className={i <= k ? 'on' : ''} />)}</span>
            </nav>
            <h1>{ep.title}</h1>
            <p className="ep-hook"><Rich text={ep.hook} facts={facts} /></p>
          </div>
          <div className="ep-icon"><ColumnIcon id={id} size={120} /></div>
        </div>
        <div className="wrap">
          <div className="col-terms col-terms--big" aria-label="이 글에서 배우는 말">
            <span>이 글에서 배우는 말</span>
            {ep.terms.map(t => <Term key={t} word={t} />)}
          </div>
        </div>
      </header>
      <article className="wrap col-read">
        {ep.qs && ep.qs.length > 0 && (
          <aside className="qs-box" aria-label="이 글이 답하는 질문">
            <b>이 글이 답하는 질문</b>
            <ul>{ep.qs.map(q => <li key={q}><span className="qs-no">{q.split(' ')[0]}</span>{q.slice(q.indexOf(' ') + 1)}</li>)}</ul>
            <span className="small">팀원들이 모은 질문 목록에서 가져왔어요.</span>
          </aside>
        )}
        <details className="src-help">
          <summary>문단 앞 표시 읽는 법</summary>
          {(['쉬운 설명', '조문', '팀 해석', '데이터'] as Source[]).map(s => <span key={s}><span className={`src ${SRC_CLASS[s]}`}>{s}</span>{s === '쉬운 설명' ? '비유로 푼 설명' : s === '조문' ? '법에 적힌 내용' : s === '팀 해석' ? '원픽 팀이 정한 해석·표시' : '원픽 분석 결과'}</span>)}
        </details>
        {ep.blocks.map((b, i) => <BlockView key={i} b={b} facts={facts} />)}
        {ep.laws.length > 0 && <Laws labels={ep.laws} />}
        <p className="small col-note">{COLUMN_NOTE}</p>
        {next ? (
          <Link to={`/column/${next.id}`} onClick={() => markRead(id)} className="next-stone" style={{ ['--u' as string]: unitOf(next.id).color, ['--ut' as string]: unitOf(next.id).tint }}>
            <span className="stone-disc"><ColumnIcon id={next.id} size={52} /></span>
            <span><span className="small">다음 글 · {themeOf(next.id).name} › {unitOf(next.id).name}</span><b>{next.title}</b></span>
          </Link>
        ) : (
          <Link to="/column" className="next-stone"><span className="stone-disc"><img src={moaSrc('happy')} alt="" width={52} /></span><span><span className="small">마지막 글까지 왔어요</span><b>칼럼 목록으로 돌아가기</b></span></Link>
        )}
      </article>
    </div>
  )
}

/** 조문 원문: 접어 두었다가 누르면 연다 */
function Laws({ labels }: { labels: string[] }) {
  const [open, setOpen] = useState(false)
  const [laws, setLaws] = useState<(Passage & { effective: string })[] | null>(null)
  useEffect(() => { if (open && !laws) api.lawPassages().then(setLaws).catch(() => setLaws([])) }, [open, laws])
  return (
    <details className="col-laws" onToggle={e => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary>📜 조문 원문 보기 <span className="small">({labels.length}개 · 원문 그대로예요. AI가 쓴 문장이 아니에요.)</span></summary>
      {!laws && <p className="small">불러오는 중…</p>}
      {laws && labels.map(l => laws.find(p => p.label === l)).filter(Boolean).map(p => (
        <article key={p!.label} className="law">
          <b>{p!.label}</b><span className="small"> · 시행 {p!.effective}</span>
          <p>{p!.text}</p>
          <a href={p!.url} target="_blank" rel="noreferrer" className="small">국가법령정보센터에서 보기 ↗</a>
        </article>
      ))}
    </details>
  )
}

function BlockView({ b, facts }: { b: Block; facts: Record<string, string | undefined> }) {
  switch (b.t) {
    case 'h': return <h2 className="col-h">{b.text}</h2>
    case 'box': return (
      <aside className={`col-box col-box--${b.kind}`}>
        <b>{b.kind === 'myth' ? '🙅 ' : b.kind === 'sum' ? '📌 ' : '💡 '}{b.title}</b>
        <ul>{b.items.map((x, i) => <li key={i}><Rich text={x} facts={facts} /></li>)}</ul>
      </aside>
    )
    case 'p':
      return <p className="col-p">{b.src && <span className={`src ${SRC_CLASS[b.src]}`}>{b.src}</span>}<Rich text={b.text} facts={facts} /></p>
    case 'say':
      return b.who === 'moa'
        ? <div className="msg with col-say"><img src={moaSrc(b.mood ?? 'base')} alt="모아" /><div><Rich text={b.text} facts={facts} /></div></div>
        : <div className="col-say col-say--me"><div className="msg me"><Rich text={b.text} facts={facts} /></div></div>
    case 'quiz': return <Quiz b={b} facts={facts} />
    case 'toy': { const T = TOYS[b.toy]; return <T /> }
    case 'link': return <p><Link className="chip" to={b.to}>{b.text}</Link></p>
  }
}

function Quiz({ b, facts }: { b: Extract<Block, { t: 'quiz' }>; facts: Record<string, string | undefined> }) {
  const [pick, setPick] = useState<number | null>(null)
  const right = pick === b.answer
  return (
    <div className="quiz" role="group" aria-label="퀴즈">
      <span className="col-no">QUIZ</span>
      <p className="quiz-q">{b.q}</p>
      <div className="chips">
        {b.options.map((o, i) => (
          <button key={o} className="chip" onClick={() => setPick(i)} aria-pressed={pick === i}
            style={pick === i ? { background: right ? 'var(--ok)' : 'var(--no)', color: '#fff' } : undefined}>{o}</button>
        ))}
      </div>
      {pick !== null && (
        <div className="moa-say" style={{ marginTop: 14 }} aria-live="polite">
          <img src={moaSrc(right ? 'happy' : 'sad')} alt="" className="moa-pop" />
          <p>{right ? '정답이에요! ' : '아쉬워요. '}<Rich text={b.why} facts={facts} /></p>
        </div>
      )}
    </div>
  )
}
