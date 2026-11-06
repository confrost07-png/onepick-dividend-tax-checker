// 내 배당 점검 챗봇의 흐름 판단: 다음에 무엇을 물을지, '내 답' 칸에 무엇을 보일지, 계산에 무엇을 보낼지, 사진을 어느 칸에 넣을지.
// 화면(Check.tsx)과 떼어 두어 화면 없이 입력 순서 조합을 돌려 볼 수 있게 한다(app/web/tests/checkFlow.test.ts).
// 지킬 약속: 챗봇이 말한 값 = '내 답'에 보이는 값 = 계산에 보내는 값.
import type { CheckupIn, EntryIntent, Script } from './api'
import { won } from './util.ts'

export interface Answers {
  holdings?: { company: string; shares: number }[]
  holdingsSkip?: '없음' | '모름' // ①에서 [없음]·[모름]을 골라 종목 없이 넘어감
  outside?: string[] // ①에 적었지만 고배당기업 목록에 없어 빼고 계산하는 종목
  receiptBracket?: string // 영수증 사진 ㉑ 총급여로 고른 ISA·IRP 구간(결과에서 미리 고르기만, 세액 계산에는 안 씀)
  interest?: number | null
  other?: { domestic: number | null; foreign: number | null }
  otherIncome?: boolean
  base?: number | null
}
export const ENTRY = -1, CONFIRM = 5, RESULT = 6

export const amountText = (v: number | null | undefined) => (v == null ? '모름' : v === 0 ? '없음' : won(v))

/** ④에 다른 소득이 있으면 ⑤ 과세표준은 묻지도, 계산에 쓰지도 않는다(근로소득 영수증만으로는 합산 세액을 알 수 없음) */
export const baseUnused = (a: Answers) => !!a.otherIncome

export const BASE_UNUSED_TAG = '계산에 안 씀'
export const NOT_ASKED = '묻지 않음'

/** '내 답' 칸 글. 아직 답하지 않았으면 null */
export function answerText(i: number, a: Answers, s: Pick<Script, 'no_wage'>): string | null {
  switch (i) {
    case 0: {
      if (!a.holdings) return null
      const out = a.outside?.length ? `${a.outside.join(', ')} (목록에 없어 뺌)` : ''
      if (!a.holdings.length) return out || (a.holdingsSkip ?? '없음')
      return [...a.holdings.map(h => `${h.company} ${h.shares.toLocaleString('ko-KR')}주`), out].filter(Boolean).join(' · ')
    }
    case 1: return a.interest === undefined ? null : amountText(a.interest)
    case 2: {
      if (!a.other) return null
      const { domestic: d, foreign: f } = a.other
      // 계산은 한쪽이라도 '모름'이면 모르는 항목으로 본다 → 화면도 '모름'으로 보인다
      if (!d && !f) return d == null || f == null ? '모름' : '없음'
      return [d !== 0 && `국내 ${amountText(d)}`, f !== 0 && `해외·ETF·펀드 ${amountText(f)}`].filter(Boolean).join(' · ')
    }
    case 3: return a.otherIncome === undefined ? null : a.otherIncome ? '있음' : '없음'
    case 4:
      if (baseUnused(a)) return a.base == null ? NOT_ASKED : `${amountText(a.base)} (${BASE_UNUSED_TAG})`
      return a.base === undefined ? null : a.base === 0 ? s.no_wage : amountText(a.base)
  }
  return null
}

/** 한 칸에 답한 뒤 갈 곳. step이 CONFIRM이면 ⑥ 확인으로 간다.
 *  otherIncomeNote: ④에 다른 소득 있음 → 비교하지 않는다는 안내를 먼저 한다
 *  reuseBase: ⑤를 묻지 않고 이미 받아 둔 과세표준(영수증 사진 등)을 쓴다 → 그 값을 알린다 */
export function nextAfter(from: number, next: Answers, editing: boolean): { step: number; otherIncomeNote: boolean; reuseBase: boolean } {
  const r = nextStep(from, next, editing)
  // ⑥으로 가려는데 아직 답하지 않은 칸이 있으면(질문 도중 앞 칸을 고친 경우 등) 그 칸부터 묻는다
  const missing = r.step === CONFIRM ? firstMissing(next) : null
  return missing == null ? r : { ...r, step: missing, reuseBase: false }
}

/** 아직 답하지 않은 첫 칸. 모두 답했으면 null (⑤는 ④가 '있음'이면 묻지 않음) */
export function firstMissing(a: Answers): number | null {
  if (!a.holdings) return 0
  if (a.interest === undefined) return 1
  if (!a.other) return 2
  if (a.otherIncome === undefined) return 3
  if (!baseUnused(a) && a.base === undefined) return 4
  return null
}

function nextStep(from: number, next: Answers, editing: boolean): { step: number; otherIncomeNote: boolean; reuseBase: boolean } {
  const otherIncomeNote = from === 3 && !!next.otherIncome
  if (from === 3 && !next.otherIncome) {
    // ④를 '없음'으로 답하거나 고쳤는데 ⑤가 비어 있으면, 고치는 중이어도 ⑤를 묻는다
    if (next.base === undefined) return { step: 4, otherIncomeNote, reuseBase: false }
    if (!editing) return { step: CONFIRM, otherIncomeNote, reuseBase: next.base != null }
  }
  if (editing || from >= 4 || otherIncomeNote) return { step: CONFIRM, otherIncomeNote, reuseBase: false }
  return { step: from + 1, otherIncomeNote, reuseBase: false }
}

/** '내 답'에서 이 칸을 고칠 수 있는지. 고칠 수 없으면 그 이유 */
export function editBlock(i: number, a: Answers): string | null {
  if (i === 4 && baseUnused(a)) return "④에서 사업·연금·기타소득이 있다고 하셔서 ⑤ 과세표준은 계산에 쓰지 않아요. 다른 소득이 없으면 먼저 ④를 눌러 고쳐 주세요."
  return null
}

/** ⑥ 확인으로 가도 되는지: ①~④는 답이 있고, ⑤는 답이 있거나 ④가 '있음' */
export function readyToConfirm(a: Answers): boolean {
  return firstMissing(a) == null
}

/** 계산 요청. ⑤는 ④가 '있음'이면 보내지 않는다(서버는 이때 과세표준을 0으로 둔다) */
export function checkupBody(a: Answers): CheckupIn {
  const holdings = a.holdings ?? []
  return {
    holdings, interest: a.interest ?? null,
    other_domestic: a.other?.domestic ?? null, other_foreign: a.other?.foreign ?? null,
    base: baseUnused(a) ? null : a.base ?? null, has_other_income: !!a.otherIncome,
    holdings_answer: holdings.length ? null : a.holdingsSkip ?? '없음',
    outside: a.outside ?? [],
  }
}

/** 영수증 사진을 지금 단계에서 받았을 때: ⑤를 묻는 중이면 입력창에 채워 확인받고(fill),
 *  아니면 ⑤ 답으로 넣어 두고(store) 그 사실을 알린다. ④가 '있음'이면 넣어 두되 계산에 쓰지 않는다고 함께 알린다 */
export function basePhoto(step: number, a: Answers, amount: number): { mode: 'fill' | 'store'; answers: Answers; say: string } {
  if (step === 4) return { mode: 'fill', answers: a, say: '' }
  const answers = { ...a, base: amount }
  const say = baseUnused(a)
    ? `⑤ 과세표준을 영수증 사진에서 읽은 ${won(amount)}으로 넣어 두었어요. 다만 ④에서 사업·연금·기타소득이 있다고 하셔서 세금 비교에는 쓰지 않아요. 다른 소득이 없으면 오른쪽 '내 답'에서 ④를 눌러 고쳐 주세요.`
    : `⑤ 과세표준을 영수증 사진에서 읽은 ${won(amount)}으로 넣어 두었어요. 영수증의 ㊼ 칸과 다르면 오른쪽 '내 답'에서 ⑤를 눌러 고쳐 주세요.`
  return { mode: 'store', answers, say }
}

// 용어 질문: '부채가 뭐예요?', '배당락 뜻', 'ETF에 대해 알려줘'처럼 용어 하나만 물었는지 본다.
// 질문하는 끝말을 떼고 남은 말이 용어 사전에 글자 그대로 있어야 용어로 본다(비슷한 말로 짐작하지 않음).
// 직접 쓴 질문과 [배당락이란?]을 누른 질문이 같은 답을 받게 하려고 한 곳에서 판단한다.
const TERM_TAILS = [
  '알려주세요', '알려줘요', '알려줄래', '알려줘', '설명해주세요', '설명해줘요', '설명해줘', '궁금해요', '궁금해',
  '무엇인가요', '무엇이에요', '무엇이야', '무엇', '뭐예요', '뭐에요', '뭔가요', '뭔데', '뭐야', '뭐지', '뭐죠', '뭐임', '뭐',
  '이라는게', '라는게', '이라는건', '라는건', '이란', '란', '뜻이', '뜻은', '뜻', '의미가', '의미는', '의미',
  '인가요', '이에요', '예요', '에대해서', '에대해',
]
const TERM_PARTICLES = ['은', '는', '이', '가', '을', '를']
const termNorm = (t: string) => t.replace(/\s/g, '').toUpperCase()

/** 용어 하나만 물었으면 용어 사전의 그 용어(이름 그대로), 아니면 null */
export function termKey(text: string, keys: string[]): string | null {
  const index = new Map(keys.map(k => [termNorm(k), k]))
  let t = termNorm(text).replace(/[?？.!~]+$/, '')
  const seen = [t]
  for (;;) {
    const w = TERM_TAILS.find(x => t.endsWith(x) && t.length > x.length)
    if (!w) break
    t = t.slice(0, -w.length)
    seen.push(t)
  }
  // 덜 뗀 말부터 본다: '공모가'처럼 끝 글자가 조사처럼 보이는 용어를 지키려고
  for (const c of seen) { const k = index.get(c); if (k) return k }
  for (const c of seen) for (const p of TERM_PARTICLES) {
    const k = c.endsWith(p) ? index.get(c.slice(0, -p.length)) : undefined
    if (k) return k
  }
  return null
}

/** 서버가 고른 기본 금융 용어 답이 같은 용어인지 ('PER(주가수익비율)'·'코스피·코스닥'은 괄호·가운뎃점으로 나눈 말 중 하나) */
export function sameTerm(faqTitle: string, key: string): boolean {
  const k = termNorm(key)
  return termNorm(faqTitle) === k || faqTitle.split(/[·()]/).some(p => termNorm(p) === k)
}

/** 시작 단계의 짧은 말이 '시작'·'거절'·'도움' 중 무엇인지. 띄어쓰기·끝 문장부호는 보지 않는다.
 *  ④에서는 '응'·'아니'가 답이라 시작 단계에서만 쓴다 */
export function entryIntent(t: string, words: Pick<Script, 'entry_words'>['entry_words']): EntryIntent | null {
  const key = t.replace(/[\s.!~?]/g, '').toLowerCase()
  for (const intent of ['start', 'decline', 'help'] as const) if (words[intent].includes(key)) return intent
  return null
}

/** 시작 단계에서 못 알아들은 말이 용어 질문처럼 보이는지 (그러면 용어 사전 안내, 아니면 일반 안내) */
export const looksLikeTerm = (t: string) => /[?？]|이란|란$|뜻|뭐야|뭔가요|뭐예요|뭐에요|무엇|알려줘|설명/.test(t.replace(/\s/g, ''))
