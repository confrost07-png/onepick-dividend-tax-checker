// 내 배당 점검 (/check, 챗봇 add-on): ①~⑤ 문답 → ⑥ 확인 → 결과.
// 답은 /api/chat/parse가 읽고, 계산은 /api/checkup이 한다. 입력은 브라우저 메모리에만 두고 저장하지 않는다.
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import type { CheckupOut, DocsGuide, Faq, ParseOut, Passage, Script } from '../api'
import { CONFIRM, ENTRY, RESULT, answerText, basePhoto, checkupBody, editBlock, entryIntent, looksLikeTerm, nextAfter, sameTerm, termKey } from '../checkFlow'
import type { Answers } from '../checkFlow'
import { GLOSSARY } from '../column'
import IsaIrpPick from '../components/IsaIrpPick'
import { usePersona } from '../persona'
import { badgeClass, moaSrc, moodOf, useLoad, won } from '../util'
import type { Mood } from '../util'

interface Msg { id: number; from: 'bot' | 'me'; text: string; mood?: Mood; note?: string; faq?: Faq; docs?: DocsGuide }
let seq = 0

// 금융 상식 칼럼 용어 사전에서 찾기: '배당락', '부채가 뭐예요?'처럼 용어만 물으면 칼럼에 써 둔 풀이를 그대로 보여 준다(새 문장을 만들지 않음)
const GLOSSARY_KEYS = Object.keys(GLOSSARY)
const GLOSSARY_N = GLOSSARY_KEYS.length
function glossaryFaq(t: string): Faq | null {
  const key = termKey(t, GLOSSARY_KEYS)
  if (!key) return null
  const g = GLOSSARY[key]
  return {
    id: `glossary-${key}`, title: key, answer: g.like ? `${g.easy} (비유하면: ${g.like})` : g.easy,
    notice: '원픽 팀이 쓴 쉬운 풀이 초안이에요(팀 검토 전). 내 경우에 맞는 세무·투자 조언은 아니에요',
    by: '금융 상식 칼럼 용어 사전에서 찾음', source_label: '원픽 금융 상식 칼럼', source_url: '/column',
  }
}

/** 용어 사전에 그대로 있는 용어를 물었으면 그 풀이. 서버가 같은 용어의 기본 금융 용어 답(출처 있음)을 골랐으면 그 답.
 *  서버의 비슷한 말 찾기가 다른 용어를 고르거나('주식' → 주식배당) 답으로 읽어도('코스피200') 용어 풀이가 먼저다 */
function termAnswer(t: string, r: ParseOut): Faq | null {
  const g = glossaryFaq(t)
  if (!g) return null
  // 같은 용어면 팀이 쓴 금융 상식 답(r.faq)을, 금융위·보충 사전 풀이(id 'term-')보다는 칼럼 용어 사전을 먼저
  return r.faq && !r.faq.id.startsWith('term-') && sameTerm(r.faq.title, g.title) ? r.faq : g
}

export default function Check() {
  const { data: s, error } = useLoad(api.script)
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [step, setStep] = useState(ENTRY)
  const [ans, setAns] = useState<Answers>({})
  const [chips, setChips] = useState<string[]>([])
  const [divType, setDivType] = useState<'domestic' | 'foreign' | null>(null)
  const [fails, setFails] = useState(0)
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [text, setText] = useState('')
  const [fresh, setFresh] = useState(-1)
  const [result, setResult] = useState<CheckupOut | null>(null)
  const [drawer, setDrawer] = useState(false)
  const [listOpen, setListOpen] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)
  const composerRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const photoKind = useRef<'holdings' | 'base'>('holdings')
  const [photoAsk, setPhotoAsk] = useState<'holdings' | 'base' | null>(null) // 사진을 고르기 전에 띄우는 안내 창
  // 로그인했다고 가정한 고객(내 정보)의 답은 단계마다 버튼으로만 보여 준다. 자동으로 채우지 않는다
  const { id: personaId } = usePersona()
  const { data: who } = useLoad(() => (personaId ? api.persona(personaId) : Promise.resolve(undefined)), [personaId])
  const mineAt = (i: number) => (i >= 0 && i < 5 ? who?.answers[i] ?? null : null)
  // 내 정보의 [이 답으로 점검 챗봇 돌려 보기](/check?auto=1): 답을 차례로 넣고 ⑥ 확인에서 멈춘다(맞아요는 고객이 누름)
  const [params, setParams] = useSearchParams()
  const auto = useRef(params.get('auto') === '1')
  const fired = useRef('')
  const chipsFor = (i: number) => {
    const qs = s?.questions[i].chips ?? []
    const mine = mineAt(i)
    return mine ? [mine, ...qs.filter(c => c !== mine)] : qs
  }

  const say = (text: string, mood: Mood = 'base', note?: string) => setMsgs(m => [...m, { id: ++seq, from: 'bot', text, mood, note }])
  const me = (text: string, note?: string) => setMsgs(m => [...m, { id: ++seq, from: 'me', text, note }])
  const showFaq = (f: Faq) => setMsgs(m => [...m, { id: ++seq, from: 'bot', text: f.answer, mood: 'happy', faq: f }])
  // 목록에서 고른 회사는 입력창 글 뒤에 이어 붙인다(앞에 고른 회사가 지워지지 않게). 목록은 열어 두고 커서는 맨 끝으로
  const addCompany = (name: string) => {
    setText(t => (t.trim() ? `${t.trim().replace(/[,·]$/, '')}, ${name} ` : `${name} `))
    setTimeout(() => { const el = inputRef.current; if (el) { el.focus(); el.setSelectionRange(el.value.length, el.value.length) } }, 0)
  }
  const termScope = () => s ? s.term_scope.replace('{glossary_n}', GLOSSARY_N.toLocaleString('ko-KR')) : ''

  function ask(i: number) {
    if (!s) return
    setStep(i); setFails(0); setDivType(null)
    // ①에는 조회할 수 있는 범위(기업 수)를, ⑤에는 영수증의 칸 번호(㊼)를 함께 알린다
    say(s.questions[i].ask, 'base', i === 0 ? s.scope_guide : i === 4 ? s.receipt_guide : undefined)
    setChips(chipsFor(i))
  }
  function confirm() {
    if (!s) return
    setStep(CONFIRM); setEditing(false)
    say(`${s.confirm_ask} 오른쪽 '내 답'에서 확인해 주세요. ${s.confirm_note}`, 'curious')
    setChips(s.confirm_chips)
  }
  function start() {
    if (!s) return
    setMsgs([]); setAns({}); setResult(null); setDrawer(false); setEditing(false)
    // 첫 질문을 바로 하지 않고 안내만 한다. [보유 종목 입력]을 누르거나 종목을 적으면 점검을 시작한다
    setStep(ENTRY); setFails(0); setDivType(null)
    say(s.greeting.replace(/^안녕하세요\.\s*/, who ? `안녕하세요, ${who.name}님! 모아예요. ` : '안녕하세요, 모아예요! '), 'happy', s.ai_note)
    say(s.start_guide)
    setChips(s.addon_chips)
  }
  useEffect(() => { if (s) start() }, [s, who?.id]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const end = endRef.current
    if (!end) return
    // 아래에 붙어 있는 입력 영역(칩·사진·입력창)에 새 말이 가려지지 않게 그 높이만큼 띄워서 맞춘다
    end.style.scrollMarginBottom = `${(composerRef.current?.offsetHeight ?? 0) + 12}px`
    // 부드러운 스크롤은 일부 브라우저(앱 안 브라우저 등)에서 아예 움직이지 않아 바로 옮긴다
    end.scrollIntoView({ block: 'nearest' })
  }, [msgs, chips])
  useEffect(() => {
    if (!auto.current || !s || !who || busy) return
    if (step === CONFIRM || step === RESULT) { auto.current = false; setParams({}, { replace: true }); return }
    const key = `${who.id}:${step}`
    const next = step === ENTRY ? s.addon_chips[0] : mineAt(step)
    if (!next || !chips.includes(next)) return
    // 같은 단계에서 다시 묻게 되면(못 읽음) 자동 진행을 끝낸다. 고객이 직접 답한 뒤에도 다시 이어 넣지 않는다
    if (fired.current === key) { auto.current = false; return }
    fired.current = key
    let done = false
    const t = setTimeout(() => { done = true; onChip(next) }, 700)
    return () => { clearTimeout(t); if (!done) fired.current = '' }
  }, [chips, busy, step, who, s]) // eslint-disable-line react-hooks/exhaustive-deps

  function advance(from: number, next: Answers) {
    if (!s) return
    const n = nextAfter(from, next, editing)
    if (n.otherIncomeNote) say(s.other_income_note, 'curious')
    // ⑤는 영수증 사진 등으로 먼저 받아 두었으면 다시 묻지 않는다
    if (n.reuseBase && next.base != null) say(`⑤ 과세표준은 앞서 받은 ${won(next.base)}을 쓸게요.`)
    if (n.step === CONFIRM) { confirm(); return }
    ask(n.step)
  }

  async function runCheckup() {
    if (!ans.holdings) return
    setBusy(true); setChips([])
    say('계산해 볼게요…', 'curious')
    try {
      const r = await api.checkup(checkupBody(ans))
      setResult(r); setStep(RESULT)
      say(r.headline, r.no_target ? 'curious' : r.tax.direction === '감소' ? 'happy' : 'base')
    } catch (e) {
      say(`계산하지 못했어요: ${(e as Error).message}`, 'sad'); setChips(s?.confirm_chips ?? [])
    } finally { setBusy(false) }
  }

  function edit(i: number) {
    if (!s || busy || step === RESULT) return
    const block = editBlock(i, ans)
    if (block) { say(block, 'curious'); return }
    setEditing(true)
    say(`${s.step_labels[i]} 항목을 다시 여쭐게요.`, 'base')
    setStep(i); setFails(0); setDivType(null)
    say(s.questions[i].ask, 'base', i === 0 ? s.scope_guide : undefined); setChips(chipsFor(i))
  }

  // 한/영 전환을 잊고 친 글을 서버가 한글로 바꿔 읽었으면, 내 말 풍선 아래에 바꾼 글을 적어 둔다
  // 오류 문구가 이미 '~주세요.'로 끝나면 '다시 알려 주세요.'를 덧붙이지 않는다
  const retryText = (error?: string) => (error && /주세요\.?$/.test(error.trim()) ? error : s ? s.parse_retry.replace('{error}', error ?? '') : '')
  const markFixed = (fixed?: string) => {
    if (s && fixed) setMsgs(m => { const i = m.map(x => x.from).lastIndexOf('me'); return m.map((x, j) => (j === i ? { ...x, note: s.layout_fixed.replace('{text}', fixed) } : x)) })
  }
  // 별칭 표로 바꾼 글을 입력창에 넣고 되묻는다(고객이 [보내기]를 눌러야 그 회사로 계산)
  const suggest = (text: string, reply?: string) => {
    say(reply ?? '', 'curious'); setText(text)
    setTimeout(() => { const el = inputRef.current; if (el) { el.focus(); el.setSelectionRange(el.value.length, el.value.length) } }, 0)
  }
  function stop() {
    if (!s) return
    auto.current = false // '그만'이면 자동 진행도 멈춘다
    setStep(ENTRY); setAns({}); setFails(0); setDivType(null); setEditing(false)
    say(s.stop_reply, 'base'); setChips(s.addon_chips)
  }

  async function submit(raw: string) {
    if (!s || busy) return
    const t = raw.trim()
    if (!t) return
    setText('')
    if (t.length > s.max_chars) { say(`${s.max_chars}자까지만 받을 수 있어요. 짧게 다시 알려 주세요.`, 'curious'); return }
    me(t)
    // 언제든: '처음부터'는 새로 시작, '그만'은 점검을 멈추고 첫 화면으로 (어느 단계에서도 갇히지 않게)
    const word = t.replace(/[.!~?\s]+$/, '')
    if (s.restart_words.includes(word)) { auto.current = false; start(); return }
    if (s.stop_words.includes(word) && step !== ENTRY) { stop(); return }
    // 버튼 이름을 그대로 적으면('보유 종목 입력', '보유종목입력') 그 버튼을 누른 것과 같게 한다
    const chip = chipFor(t)
    if (chip && chipAction(chip)) return
    if (step === RESULT) return
    if (step === CONFIRM) {
      if (t === s.confirm_chips[0] || s.confirm_yes.includes(word)) { runCheckup(); return }
      if (t === s.confirm_chips[1] || s.confirm_no.includes(word)) { say(`${s.edit_ask} 오른쪽 '내 답'에서 고칠 칸을 누르거나 아래에서 골라 주세요.`, 'curious'); setChips(s.step_labels.slice(0, 5)); return }
      const k = s.step_labels.indexOf(t)
      if (k >= 0 && k < 5) { edit(k); return }
      say('[맞아요]나 [고칠게요]를 눌러 주세요.', 'curious'); setChips(s.confirm_chips); return
    }
    if (step === ENTRY) { await onEntry(t); return }
    const q = s.questions[step]
    // ③ 다른 배당: 종류만 고르면 금액을 따로 묻는다
    if (q.kind === 'other_dividend' && !divType && !/\d/.test(t) && s.dividend_types[t]) {
      setDivType(s.dividend_types[t])
      say(s.dividend_amount_ask.replace('{kind}', t)); setChips(s.dividend_amount_chips); return
    }
    if (q.kind === 'base' && t === s.receipt_chip) { say(s.receipt_guide, 'curious'); return }

    setBusy(true)
    try {
      const r = await api.parse(q.kind, t, divType)
      markFixed(r.fixed_text)
      const term = termAnswer(t, r)
      if (term) { showFaq(term); say(q.ask); setChips(chipsFor(step)); return }
      if (r.guard) { say(r.reply ?? '', 'curious'); if (r.consult) setChips(['세무상담 예약신청', ...q.chips]); return }
      if (r.chat) { say(r.chat, 'happy'); say(q.ask); setChips(chipsFor(step)); return }
      if (r.suggest_text) { suggest(r.suggest_text, r.reply); return }
      if (r.question) {
        // 답이 아니라 질문: 미리 써 둔 금융 상식 답을 그대로 보여 주거나(AI는 고르기만 함), 이 단계 도움말을 보여 주고 같은 질문을 다시 한다
        if (r.faq) showFaq(r.faq)
        else say(r.help ?? s.step_help[q.kind], 'curious')
        say(q.ask); setChips(chipsFor(step)); return
      }
      if (r.add_holdings) {
        // ③에 '종목 + 주식 수'를 적음: 조회 대상 회사면 ① 종목에 더하고, ③을 다시 묻는다(금액으로 읽지 않음)
        const cur = ans.holdings ?? []
        const added = r.add_holdings.filter(h => !cur.some(x => x.company === h.company))
        const dup = r.add_holdings.filter(h => cur.some(x => x.company === h.company))
        if (added.length) {
          setAns({ ...ans, holdings: [...cur, ...added], holdingsSkip: undefined }); setFresh(0)
          say(s.other_holding_added.replace('{names}', added.map(h => h.company).join(', ')), 'happy')
        }
        if (dup.length) say(s.other_holding_dup.replace('{names}', dup.map(h => h.company).join(', ')), 'curious')
        setDivType(null); say(q.ask); setChips(chipsFor(step)); return
      }
      if (r.prompt) { say(r.prompt, 'curious'); return }
      if (!r.ok) {
        const n = fails + 1
        setFails(n)
        say(retryText(r.error), 'curious', n >= 3 ? s.stuck_hint : undefined)
        return
      }
      if (r.by === 'AI') setMsgs(m => m.map((x, i) => (i === m.length - 1 ? { ...x, note: s.ai_read_mark } : x)))
      const next: Answers = { ...ans }
      if (q.kind === 'holdings') {
        next.holdings = r.value as Answers['holdings']
        next.holdingsSkip = r.skip
        next.outside = r.excluded
        if (r.skip && r.reply) say(r.reply)
        if (r.note) say(r.note, 'curious') // 목록에 없는 종목은 빼고 넘어감
      }
      else if (q.kind === 'amount') next.interest = r.value as number | null
      else if (q.kind === 'other_dividend') next.other = r.value as Answers['other']
      else if (q.kind === 'yesno') next.otherIncome = r.value as boolean
      else next.base = r.value as number | null
      setAns(next); setFresh(step)
      advance(step, next)
    } catch (e) {
      say(`잠시 연결이 안 돼요: ${(e as Error).message}`, 'sad')
    } finally { setBusy(false) }
  }

  // 시작 단계: 종목을 적으면 ①의 답으로 받고, 질문이면 금융 상식 답, 아니면 안내를 다시 한다
  async function onEntry(t: string) {
    if (!s) return
    // '시작'·'응'은 [보유 종목 입력]과 같게, '아니'·'도와줘'는 정해 둔 답
    const intent = entryIntent(t, s.entry_words)
    if (intent === 'start') { ask(0); return }
    if (intent) { say(s.entry_replies[intent]); setChips(s.addon_chips); return }
    setBusy(true)
    try {
      const r = await api.parse('holdings', t)
      markFixed(r.fixed_text)
      const term = termAnswer(t, r)
      if (term) { showFaq(term); setChips(s.addon_chips); return }
      const f = r.guard || r.chat || r.ok ? null : r.faq
      if (r.guard) say(r.reply ?? '', 'curious')
      else if (r.chat) say(r.chat, 'happy')
      else if (r.suggest_text) { suggest(r.suggest_text, r.reply); return }
      else if (f) showFaq(f)
      else if (r.ok) {
        const next: Answers = { ...ans, holdings: r.value as Answers['holdings'], holdingsSkip: r.skip, outside: r.excluded }
        if (r.skip && r.reply) say(r.reply)
        if (r.note) say(r.note, 'curious') // 목록에 없는 종목은 빼고 넘어감
        setAns(next); setFresh(0); advance(0, next); return
      } else if (r.code === 'not_found') say(retryText(r.error), 'curious')
      else if (r.code === 'missing_shares' || r.code === 'bad_shares' || r.code === 'missing_name') say(r.error ?? '', 'curious') // 주식 수·종목 이름이 빠졌거나 0주·음수: 되묻는다
      else say(looksLikeTerm(t) ? s.entry_fallback : s.entry_unclear, 'curious') // 용어 질문처럼 보일 때만 용어 사전 안내
      setChips(s.addon_chips)
    } catch (e) {
      say(`잠시 연결이 안 돼요: ${(e as Error).message}`, 'sad')
    } finally { setBusy(false) }
  }

  // 사진 넣기 — 보유 종목 캡처와 원천징수영수증 2쪽(㊼ 칸만)을 점검 중 언제든 넣는다. 긴 변 1600px JPEG로 줄여
  // 서버 안 AI에 보낸다. 지금 묻는 칸의 사진이면 읽은 글을 입력창에 채워 고객이 확인한 뒤 보내고,
  // 다른 칸의 사진이면 그 칸 답으로 넣어 두고 '내 답'에서 고칠 수 있게 알린다
  const pickPhoto = (kind: 'holdings' | 'base') => { photoKind.current = kind; fileRef.current?.click() }
  async function onImage(file: File | undefined) {
    if (!s || !file) return
    const base = photoKind.current === 'base'
    const here = base ? step === 4 : step === ENTRY || step === 0
    setBusy(true); setListOpen(false)
    me(base ? '📷 원천징수영수증 2쪽' : '📷 보유 종목 사진', base ? s.base_image_note : s.image_note)
    say(base ? s.base_image_reading : s.image_reading)
    try {
      const photo = await shrink(file)
      const r = await (base ? api.baseImage(photo) : api.holdingsImage(photo))
      if (!r.ok || !r.text) { say(r.error ?? '', 'curious'); return }
      if (base && r.bracket) setAns(a => ({ ...a, receiptBracket: r.bracket })) // 결과의 ISA·IRP 구간을 미리 고르는 데만 쓴다
      if (here) {
        say(r.reply ?? '', r.missing?.length ? 'curious' : 'happy')
        setText(r.text)
        setTimeout(() => { const el = inputRef.current; if (el) { el.focus(); el.setSelectionRange(el.value.length, el.value.length) } }, 0)
      } else if (base) {
        const amount = r.amount
        if (amount == null) { say(r.error ?? '', 'curious'); return }
        const b = basePhoto(step, ans, amount)
        setAns({ ...b.answers, receiptBracket: r.bracket ?? b.answers.receiptBracket }); setFresh(4)
        say(b.say, b.answers.otherIncome ? 'curious' : 'happy')
      } else {
        const p = await api.parse('holdings', r.text)
        if (!p.ok) { say(`사진에서 ${r.text}로 읽었는데, ${p.error ?? '확인이 필요해요'}. 오른쪽 '내 답'에서 ①을 눌러 고쳐 주세요.`, 'curious'); return }
        setAns(a => ({ ...a, holdings: p.value as Answers['holdings'], holdingsSkip: undefined, outside: p.excluded }))
        say(`① 보유 종목을 사진에서 읽은 대로 넣어 두었어요: ${r.text}. 틀리면 오른쪽 '내 답'에서 ①을 눌러 고쳐 주세요.`, 'happy')
      }
    } catch (e) {
      say(`잠시 연결이 안 돼요: ${(e as Error).message}`, 'sad')
    } finally { setBusy(false); if (fileRef.current) fileRef.current.value = '' }
  }

  // 버튼만의 동작(질문으로 읽지 않는 것). 했으면 true. before: 답하기 전에 할 일(누른 버튼을 고객 말풍선으로 남기기)
  const chipAction = (c: string, before = () => {}): boolean => {
    if (!s) return false
    const known = c === s.docs_chip || c === s.term_chip || c === '세무상담 예약신청'
      || (step === ENTRY && (c === s.addon_chips[0] || !!s.addon_replies[c]))
    if (!known) return false
    before()
    // 필요서류 발급은 어느 단계에서나 공식 발급 창구를 안내한다(원픽이 발급하지 않음)
    if (c === s.docs_chip) { setMsgs(m => [...m, { id: ++seq, from: 'bot', text: s.docs_guide.text, mood: 'happy', docs: s.docs_guide }]); return true }
    if (c === s.term_chip) { say(termScope(), 'curious'); setChips(step === ENTRY ? [...s.term_examples, s.addon_chips[0]] : s.term_examples); return true }
    if (step === ENTRY && c === s.addon_chips[0]) { ask(0); return true }
    if (step === ENTRY && s.addon_replies[c] && c !== '세무상담 예약신청') { say(s.addon_replies[c]); return true }
    say('점검을 마치면 결과 아래 버튼으로 세무상담 신청 화면(모형)에 결과를 함께 가져갈 수 있어요. 바로 가려면 위 메뉴의 \'자산관리\'를 눌러 주세요.') // 세무상담 예약신청
    return true
  }
  // 적은 글이 버튼 이름과 같은지 (띄어쓰기·끝 문장부호는 보지 않는다)
  const chipFor = (t: string) => {
    if (!s) return undefined
    const key = (x: string) => x.replace(/[\s.!~]/g, '')
    return [s.docs_chip, s.term_chip, ...s.addon_chips, '세무상담 예약신청'].find(c => key(c) === key(t))
  }
  const onChip = (c: string) => {
    if (!chipAction(c, () => me(c))) submit(c)
  }

  if (error) return <div className="wrap"><p className="error">{error}</p></div>
  if (!s) return <div className="wrap loading">불러오는 중…</div>

  const done = (i: number) => answerText(i, ans, s) != null
  return (
    <div className="wrap">
      <div className="check-head">
        <h1>{s.title}</h1>
        <p className="small" style={{ margin: 0 }}>{s.result_lead} 입력은 계산에만 쓰고 저장하지 않아요(<Link to="/privacy">개인정보 처리 안내</Link>).</p>
      </div>
      <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={6} aria-valuenow={Math.min(step, 6)} aria-label="점검 진행">
        {s.step_labels.map((l, i) => <span key={l} title={l} className={i < step || (i < 5 && done(i) && step >= CONFIRM) ? 'done' : i === step ? 'now' : ''} />)}
      </div>
      <div className="check">
        <section>
          <div className="chat" aria-live="polite">
            {msgs.map(m => m.from === 'bot' ? (
              <div key={m.id} className="msg with"><img src={moaSrc(m.mood ?? 'base')} alt="" /><div>
                {m.faq && <b className="faq-title">📘 {m.faq.title}</b>}
                {m.text}{m.note && <small style={{ marginTop: 6 }}>{m.note}</small>}
                {m.docs && <ol className="docs-guide">{m.docs.items.map(d => (
                  <li key={d.title}><b>{d.title}</b><span>{d.how}</span>
                    <span className="docs-links">{d.links.map(l => <a key={l.url} href={l.url} target="_blank" rel="noreferrer">{l.label} 열기 ↗</a>)}</span></li>
                ))}</ol>}
                {m.docs && <small style={{ marginTop: 6 }}>{m.docs.note}</small>}
                {m.faq && <small className="faq-note">{m.faq.notice} · {m.faq.by} · 출처: <a href={m.faq.source_url} target="_blank" rel="noreferrer">{m.faq.source_label}</a></small>}
              </div></div>
            ) : (
              <div key={m.id} className="msg me">{m.text}{m.note && <small>{m.note}</small>}</div>
            ))}
            <div ref={endRef} />
          </div>
          {step !== RESULT && (
            <div className="composer" ref={composerRef}>
              {chips.length > 0 && <div className="chips">{chips.map(c => <button key={c} className={`chip${c === mineAt(step) ? ' chip--mine' : ''}`} title={c === mineAt(step) ? `${who?.name}님의 답` : undefined} disabled={busy} onClick={() => onChip(c)}>{c === mineAt(step) && <span className="chip-mine-tag">내 답</span>}{c}</button>)}</div>}
              {listOpen && <CompanyList close={() => setListOpen(false)} pick={addCompany} />}
              <div className="tool-row">
              {(step === ENTRY || step === 0 || step === 2) && (
                <button type="button" className="list-btn" aria-expanded={listOpen} onClick={() => setListOpen(o => !o)}>📋 {s.company_list_chip} 보기</button>
              )}
              {step !== RESULT && (
                <>
                  <button type="button" className="list-btn" disabled={busy} onClick={() => setPhotoAsk('holdings')}>📷 {s.image_chip}</button>
                  <button type="button" className="list-btn" disabled={busy} onClick={() => setPhotoAsk('base')}>🧾 {s.base_image_chip}</button>
                  <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={e => onImage(e.target.files?.[0])} />
                  {photoAsk && <PhotoGuide kind={photoAsk} s={s} close={() => setPhotoAsk(null)} pick={() => { const k = photoAsk; setPhotoAsk(null); pickPhoto(k) }} />}
                </>
              )}
              </div>
              <form onSubmit={e => { e.preventDefault(); auto.current = false; submit(text) }}>
                <label className="sr" htmlFor="say">답 입력</label>
                <input id="say" ref={inputRef} value={text} maxLength={s.max_chars + 20} disabled={busy} onChange={e => setText(e.target.value)} placeholder={step === ENTRY ? '예: 배당락이란? · 삼성전자 10주' : '예: 100주 · 500만 원 · 모름'} autoComplete="off" />
                <button className="btn" disabled={busy || !text.trim()}>보내기</button>
              </form>
            </div>
          )}
        </section>
        <aside className="mine" aria-label="내 답">
          <h4>내 답</h4>
          <dl>
            {s.step_labels.slice(0, 5).map((l, i) => {
              const v = answerText(i, ans, s)
              return (
                <button key={l} className={fresh === i ? 'fresh' : ''} disabled={v == null || busy || step === RESULT} onClick={() => edit(i)} aria-label={`${l} ${v ?? '아직 안 물어봄'}${v ? ', 눌러서 고치기' : ''}`}>
                  <dt>{l}</dt><dd>{v ?? '–'}</dd>
                </button>
              )
            })}
          </dl>
          <p className="small" style={{ margin: '10px 0 0' }}>답한 칸을 누르면 그 항목만 다시 물어요. 입력은 저장하지 않아요.</p>
        </aside>
      </div>

      {result && <Result r={result} s={s} drawer={drawer} setDrawer={setDrawer} restart={start}
        bracket={ans.otherIncome ? undefined : ans.receiptBracket}
        fin={(ans.interest ?? 0) + (ans.other?.domestic ?? 0) + (ans.other?.foreign ?? 0) + result.special_total} />}
    </div>
  )
}

// 종목별 풀이: '30주 · 특례배당 750원 · 2027엔 2025년의 110% 필요'를 금융 용어 없이 문장으로
function stockLines(st: CheckupOut['stocks'][number], t: Script['stock_text']): string[] {
  const n = (v: number) => v.toLocaleString('ko-KR', { maximumFractionDigits: 1 })
  const out = [t.shares.replace('{shares}', st.shares.toLocaleString('ko-KR'))]
  if (st.special) out.push(t.special.replace('{amount}', won(st.special)))
  if (st.held) out.push(t.held.replace('{amount}', won(st.held)))
  if (!st.special && !st.held) out.push(t.general)
  const r = st.ratio_to_2025_pct
  if (st.need_2027 != null && st.d2025 != null && r != null) {
    out.push(r > 100 ? t.next_up.replace('{pct}', n(r - 100)) : t.next_keep.replace('{pct}', n(r)))
  }
  return out
}

function Result({ r, s, drawer, setDrawer, restart, fin, bracket }: { r: CheckupOut; s: Script; drawer: boolean; setDrawer: (v: boolean) => void; restart: () => void; fin: number; bracket?: string }) {
  const [send, setSend] = useState(false)
  const nav = useNavigate()
  // 점검 결과는 주소(URL)에 싣지 않고 화면 사이에서만 넘긴다. 저장하지 않는다.
  const toConsult = (type: 'separate' | 'filing') => nav(`/consult?type=${type}`, { state: { send, checkup: {
    headline: r.headline,
    diff: r.tax.difference != null ? `${won(Math.abs(r.tax.difference))} (${r.tax.direction})` : null,
    stocks: r.stocks.map(x => `${x.name} ${x.status}`),
  } } })
  return (
    <div className={`result${drawer ? '' : ' result--solo'}`}>
      <section className="card" aria-label="점검 결과">
        <span className="tag">점검 결과 · 판정은 실제 공시, 세액은 참고 계산</span>
        <p className="big" style={{ fontSize: 26 }}>{r.headline}</p>
        {r.no_target ? (
          // 특례 대상 배당이 없음: 계산하지 않은 이유를 보여 준다
          <div className="taxbig"><span className="small" style={{ fontWeight: 800 }}>{s.special_label}</span><br />
            <b className="num">{s.no_target}</b>
            <p className="small" style={{ margin: '6px 0 0' }}>{r.no_target}</p></div>
        ) : r.tax.difference != null ? (
          <div className="taxbig"><span className="small" style={{ fontWeight: 800 }}>분리과세를 신청하면 계산상 세액 차이</span><br />
            <b className="num">{won(Math.abs(r.tax.difference))} ({r.tax.direction})</b>
            <p className="small" style={{ margin: '6px 0 0' }}>참고용 모의 계산이에요. 확정 세액이나 돌려받는 돈(환급액)이 아니에요.</p></div>
        ) : (
          <div className="taxbig">
            <span className="small" style={{ fontWeight: 800 }}>{s.special_label}</span>
            <span className="small legal"> · {s.special_legal}</span><br /><b className="num">{won(r.special_total)}</b><br />
            <span className="small" style={{ fontWeight: 800, display: 'inline-block', marginTop: 10 }}>{s.special_tax_label}</span><br />
            <b className="num">{won(r.tax.separate_tax)}</b> <span className="small">({s.special_tax_tag})</span>
            <p className="small" style={{ margin: '8px 0 0' }}>{s.special_tax_note}</p>
          </div>
        )}
        {r.tax.difference != null && !r.no_target && (
          <div className="rows">{r.tax.rows.map(([k, v]) => <div key={k}><span>{k}</span><span className="num">{won(v)}</span></div>)}</div>
        )}
        <details className="explain">
          <summary>{s.special_explain_title}</summary>
          {s.special_explain.map(p => <p key={p} className="small">{p}</p>)}
        </details>
        <div className="stocks">
          {r.stocks.map(st => (
            <div key={st.name}>
              <img src={moaSrc(moodOf(st.status))} alt="" />{st.name}
              <span className={`badge ${badgeClass(st.status)}`}>{st.status}{st.route ? ` · ${st.route}` : ''}</span>
              <small className="stock-plain">{stockLines(st, s.stock_text).map(l => <span key={l}>{l}</span>)}</small>
            </div>
          ))}
        </div>
        <p className="small" style={{ margin: '12px 0 0' }}>{s.condition} {s.next_check}</p>
        <label className="small" style={{ display: 'flex', gap: 8, margin: '14px 0 0', fontWeight: 700 }}>
          <input type="checkbox" checked={send} onChange={e => setSend(e.target.checked)} /> {s.send_result}
        </label>
        <p className="small" style={{ margin: '4px 0 0' }}>{s.send_result_note}</p>
        {r.tax.status === '차이 없음' && <IsaIrpPick fin={fin} preset={bracket} />}
        <div className="outlinks">
          <button className="btn btn--sm" onClick={() => toConsult('separate')}>{s.result_actions[0]}</button>
          <button className="btn btn--soft btn--sm" onClick={() => toConsult('filing')}>{s.result_actions[1]}</button>
          <button className="chip" onClick={() => setDrawer(!drawer)} aria-expanded={drawer}>근거 보기</button>
          <button className="chip" onClick={restart}>처음부터 다시 점검</button>
        </div>
        <p className="small" style={{ margin: '14px 0 0' }}>{r.notes.join(' ')} {s.result_footnote}</p>
      </section>
      {drawer && <Evidence s={s} close={() => setDrawer(false)} />}
    </div>
  )
}

// 조회 대상 기업 목록: 입력창 위에 펼친다. 이름을 누르면 입력창에 이어 붙이고(여러 개 가능), 주식 수는 고객이 이어서 적는다
function CompanyList({ pick, close }: { pick: (name: string) => void; close: () => void }) {
  const { data, error } = useLoad(api.companyList)
  const [q, setQ] = useState('')
  const k = q.replace(/\s/g, '').toUpperCase()
  const shown = (data ?? []).filter(c => !k || c.name.replace(/\s/g, '').toUpperCase().includes(k) || c.code.startsWith(k))
  const ul = useRef<HTMLUListElement>(null)
  const prefs = (data ?? []).filter(c => c.pref_of).length
  const firms = (data ?? []).length - prefs
  // 긴 이름은 줄바꿈·말줄임 대신 칸 너비에 맞춰 글자를 줄인다(최소 11px). 칸 크기는 CSS가 고정한다
  useEffect(() => {
    const box = ul.current
    if (!box) return
    const fit = () => {
      const names = [...box.querySelectorAll<HTMLElement>('.company-list__name')]
      names.forEach(n => { n.style.fontSize = '' })
      const sizes = names.map(n => n.scrollWidth > n.clientWidth
        ? Math.max(11, Math.floor(parseFloat(getComputedStyle(n).fontSize) * n.clientWidth / n.scrollWidth * 10) / 10) : 0)
      names.forEach((n, i) => { if (sizes[i]) n.style.fontSize = `${sizes[i]}px` })
    }
    fit()
    document.fonts.ready.then(fit)  // 웹 글꼴이 늦게 오면 글자 폭이 바뀐다
    // 목록 폭이 그대로여도 열 수가 바뀌면 카드 폭이 바뀌므로 첫 카드도 지켜본다
    const ro = new ResizeObserver(fit)
    ro.observe(box)
    if (box.firstElementChild) ro.observe(box.firstElementChild)
    return () => ro.disconnect()
  }, [shown.length, k])
  return (
    <div className="company-list" role="dialog" aria-label="조회 대상 기업 목록">
      <div className="company-list__head">
        <b>조회 대상 기업 {data ? `${firms.toLocaleString('ko-KR')}곳${prefs ? ` · 우선주 ${prefs.toLocaleString('ko-KR')}종목` : ''}` : ''}</b>
        <button type="button" onClick={close} aria-label="닫기">×</button>
      </div>
      <input value={q} onChange={e => setQ(e.target.value)} placeholder="기업명이나 종목코드로 찾기" aria-label="목록에서 찾기" autoFocus />
      {error && <p className="small error">{error}</p>}
      {!data && !error && <p className="small">불러오는 중…</p>}
      {data && !shown.length && <p className="small">조회 결과가 없습니다. 기업명 표기를 확인해 주세요.</p>}
      <ul ref={ul}>{shown.map(c => <li key={c.name}><button type="button" onClick={() => pick(c.name)} title={c.pref_of ? `${c.pref_of}의 우선주` : c.name}><span className="company-list__name">{c.name}</span><small>{c.pref_of ? `우선주 · ${c.code}` : c.code}</small></button></li>)}</ul>
      <p className="small" style={{ margin: 0 }}>이름을 누르면 입력창에 이어서 넣어 드려요. 회사마다 이름 뒤에 주식 수를 적어 주세요(예: 삼성전자 100주, 케이티앤지 30주).</p>
    </div>
  )
}

/** 사진 넣기 전 안내 창: 무엇을 찍을지, 어느 칸만 읽는지, 저장하지 않는다는 것을 먼저 보여 주고 [사진 고르기]로 파일을 고른다 */
function PhotoGuide({ kind, s, close, pick }: { kind: 'holdings' | 'base'; s: Script; close: () => void; pick: () => void }) {
  const g = s.image_guide[kind]
  const pickRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    pickRef.current?.focus()
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [close])
  return (
    <div className="photo-guide-bg" onClick={close}>
      <div className="photo-guide" role="dialog" aria-modal="true" aria-labelledby="photo-guide-title" onClick={e => e.stopPropagation()}>
        <h4 id="photo-guide-title">{kind === 'base' ? '🧾' : '📷'} {g.title}</h4>
        <ul>{g.lines.map(l => <li key={l}>{l}</li>)}</ul>
        <div className="photo-guide-btns">
          <button type="button" className="btn btn--soft btn--sm" onClick={close}>취소</button>
          <button type="button" ref={pickRef} className="btn btn--sm" onClick={pick}>{s.image_guide_pick}</button>
        </div>
      </div>
    </div>
  )
}

function Evidence({ s, close }: { s: Script; close: () => void }) {
  const { data } = useLoad(api.evidence)
  const [q, setQ] = useState('')
  const [hits, setHits] = useState<Passage[] | null>(null)
  const find = async (e: React.FormEvent) => {
    e.preventDefault()
    if (q.trim()) setHits((await api.lawSearch(q.trim()).catch(() => ({ hits: [] as Passage[] }))).hits)
  }
  return (
    <aside className="drawer" aria-label="근거 보기">
      <h4>근거 보기 <button onClick={close} aria-label="닫기">×</button></h4>
      <div className="orig">원문 그대로예요. AI가 쓴 문장이 아니에요.</div>
      {(data ?? []).map(p => <article key={p.label}><b>{p.label}</b><p>{p.text}</p></article>)}
      <form onSubmit={find}>
        <label className="sr" htmlFor="lawq">관련 조문 찾기</label>
        <input id="lawq" value={q} onChange={e => setQ(e.target.value)} placeholder="관련 조문 찾기 (예: 고배당 분리과세 신청)" maxLength={s.max_chars} />
        <button className="btn btn--sm">찾기</button>
      </form>
      {hits && (hits.length ? hits.map(p => <article key={p.label}><b>{p.label}</b> <span className="small">{p.by}</span><p>{p.text}</p></article>)
        : <p className="small">비슷한 조문을 찾지 못했어요.</p>)}
      <p className="small" style={{ margin: '10px 0 0' }}>{s.law_notice}</p>
    </aside>
  )
}

/** 사진을 긴 변 1600px 이하 JPEG(data URL)로 줄인다. 큰 캡처도 빨리 보내고, 서버는 JPEG만 받으면 된다 */
async function shrink(file: File, max = 1600): Promise<string> {
  const bmp = await createImageBitmap(file)
  const k = Math.min(1, max / Math.max(bmp.width, bmp.height))
  const c = document.createElement('canvas')
  c.width = Math.round(bmp.width * k); c.height = Math.round(bmp.height * k)
  c.getContext('2d')!.drawImage(bmp, 0, 0, c.width, c.height)
  bmp.close()
  return c.toDataURL('image/jpeg', 0.9)
}
