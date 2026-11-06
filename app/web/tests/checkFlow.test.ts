// 점검 챗봇 흐름 검증 (실행: cd app/web && node --test tests/checkFlow.test.ts)
// Check.tsx가 쓰는 흐름 판단(src/checkFlow.ts)을 화면 없이 돌린다. 답·사진·고치기를 아무 순서로 섞은 입력 수만 가지에서
// '챗봇이 말한 값 = 내 답 칸 = 계산에 보낸 값'과 '④ 있음이면 ⑤를 묻지도 쓰지도 않음'이 늘 지켜지는지 본다.
import assert from 'node:assert/strict'
import test from 'node:test'
import {
  BASE_UNUSED_TAG, CONFIRM, ENTRY, NOT_ASKED, amountText, answerText, basePhoto, checkupBody, editBlock, nextAfter, readyToConfirm,
  sameTerm, termKey,
} from '../src/checkFlow.ts'
import type { Answers } from '../src/checkFlow.ts'

const S = { no_wage: '근로소득 없음' }

interface State { step: number; ans: Answers; editing: boolean }

// Check.tsx의 submit → advance와 같은 순서로 한 칸 답을 넣는다
function answer(st: State, value: unknown): State {
  const next: Answers = { ...st.ans }
  const at = st.step === ENTRY ? 0 : st.step
  if (at === 0) { next.holdings = value as Answers['holdings']; next.holdingsSkip = undefined }
  else if (at === 1) next.interest = value as number | null
  else if (at === 2) next.other = value as Answers['other']
  else if (at === 3) next.otherIncome = value as boolean
  else next.base = value as number | null
  const n = nextAfter(at, next, st.editing)
  return n.step === CONFIRM ? { step: CONFIRM, ans: next, editing: false } : { step: n.step, ans: next, editing: st.editing }
}

function rng(seed: number) {
  let x = seed >>> 0 || 1
  return () => { x ^= x << 13; x >>>= 0; x ^= x >>> 17; x ^= x << 5; x >>>= 0; return x / 2 ** 32 }
}
const pick = <T,>(r: () => number, xs: T[]): T => xs[Math.floor(r() * xs.length)]

const VALUES: Record<number, unknown[]> = {
  0: [[{ company: '두산2우B', shares: 100 }], [{ company: '삼성전자', shares: 6000 }, { company: '삼성전자우', shares: 6000 }], []],
  1: [null, 0, 6_000_000],
  2: [{ domestic: 0, foreign: 0 }, { domestic: null, foreign: null }, { domestic: 3_000_000, foreign: null }, { domestic: null, foreign: 0 }, { domestic: 300_000, foreign: 200_000 }],
  3: [true, false],
  4: [null, 0, 30_000_000],
}

function checkConfirm(st: State, where: string) {
  const a = st.ans
  assert.ok(readyToConfirm(a), `${where}: ⑥ 확인인데 빈 칸이 있음 ${JSON.stringify(a)}`)
  for (let i = 0; i < 5; i++) assert.notEqual(answerText(i, a, S), null, `${where}: 내 답 ${i + 1}번 칸이 비어 있음`)
  const body = checkupBody(a)
  const shown = answerText(4, a, S)!
  assert.equal(body.has_other_income, !!a.otherIncome)
  if (a.otherIncome) {
    assert.equal(body.base, null, `${where}: ④ 있음인데 ⑤를 보냄`)
    assert.ok(shown === NOT_ASKED || shown.includes(BASE_UNUSED_TAG), `${where}: ④ 있음인데 ⑤ 칸이 쓰는 것처럼 보임: ${shown}`)
  } else {
    assert.notEqual(a.base, undefined)
    assert.equal(body.base, a.base ?? null, `${where}: ⑤ 칸과 보낸 값이 다름`)
    assert.equal(shown, a.base === 0 ? S.no_wage : amountText(a.base), `${where}: ⑤ 칸 글이 값과 다름`)
  }
}

test('보내 주신 화면 그대로: ④ 있음 → ⑥ 확인에서 영수증 사진 → 넣었다고 하면서 쓰지 않는다고 함께 알린다', () => {
  let st: State = { step: 0, ans: {}, editing: false }
  for (const v of [VALUES[0][1], 6_000_000, { domestic: 0, foreign: 0 }, true]) st = answer(st, v)
  assert.equal(st.step, CONFIRM)
  assert.equal(answerText(4, st.ans, S), NOT_ASKED)
  const b = basePhoto(st.step, st.ans, 56_831_000)
  assert.equal(b.mode, 'store')
  assert.match(b.say, /쓰지 않아요/)
  assert.equal(answerText(4, b.answers, S), `56,831,000원 (${BASE_UNUSED_TAG})`)
  assert.equal(checkupBody(b.answers).base, null)
  assert.match(editBlock(4, b.answers) ?? '', /④를 눌러 고쳐/)
  // ④를 '없음'으로 고치면 ⑤를 다시 묻지 않고 사진 값을 쓴다
  st = answer({ step: 3, ans: b.answers, editing: true }, false)
  assert.equal(st.step, CONFIRM)
  assert.equal(checkupBody(st.ans).base, 56_831_000)
  checkConfirm(st, '④ 고침')
})

test('④를 있음 → 없음으로 고쳤는데 ⑤가 비어 있으면 ⑤를 묻는다', () => {
  let st: State = { step: 0, ans: {}, editing: false }
  for (const v of [VALUES[0][0], 0, { domestic: 0, foreign: 0 }, true]) st = answer(st, v)
  st = answer({ ...st, step: 3, editing: true }, false)
  assert.equal(st.step, 4)
  st = answer(st, 40_000_000)
  assert.equal(st.step, CONFIRM)
  checkConfirm(st, '⑤ 답함')
})

test('영수증 사진을 ⑤보다 먼저 넣으면 ⑤를 묻지 않고 그 값을 쓴다고 알린다', () => {
  let st: State = { step: 0, ans: {}, editing: false }
  st = answer(st, VALUES[0][0])
  st = { ...st, ans: basePhoto(st.step, st.ans, 51_000_000).answers }
  for (const v of [0, { domestic: 0, foreign: 0 }]) st = answer(st, v)
  const n = nextAfter(3, { ...st.ans, otherIncome: false }, false)
  assert.deepEqual([n.step, n.reuseBase], [CONFIRM, true])
})

test('입력 순서를 아무렇게나 섞어도(2만 가지) 말·칸·계산 값이 어긋나지 않는다', () => {
  const r = rng(20261102)
  let confirms = 0, photos = 0
  for (let run = 0; run < 20000; run++) {
    let st: State = { step: ENTRY, ans: {}, editing: false }
    const trail: string[] = []
    for (let t = 0; t < 40; t++) {
      const where = `#${run} ${trail.join(' → ')}`
      const ev = r()
      if (ev < 0.15) { // 영수증 사진 (어느 단계에서나)
        const amount = pick(r, [12_340_000, 56_831_000])
        const b = basePhoto(st.step, st.ans, amount)
        trail.push(`영수증@${st.step}`); photos++
        if (b.mode === 'fill') st = answer(st, amount) // ⑤를 묻는 중: 입력창에 채운 값을 고객이 보냄
        else {
          assert.equal(b.say.includes('쓰지 않아요'), !!b.answers.otherIncome, `${where}: 사진 안내가 계산 사용 여부와 다름`)
          assert.ok(answerText(4, b.answers, S)!.includes(amountText(amount)), `${where}: 넣었다는 값이 내 답 칸에 없음`)
          st = { ...st, ans: b.answers }
        }
      } else if (ev < 0.22) { // 보유 종목 사진
        const h = pick(r, VALUES[0]) as Answers['holdings']
        trail.push(`종목사진@${st.step}`)
        st = st.step === ENTRY || st.step === 0 ? answer(st, h) : { ...st, ans: { ...st.ans, holdings: h, holdingsSkip: undefined } }
      } else if (st.step === CONFIRM) {
        if (r() < 0.35) { trail.push('맞아요'); checkConfirm(st, where); confirms++; break }
        const i = Math.floor(r() * 5)
        trail.push(`고치기${i + 1}`)
        if (answerText(i, st.ans, S) == null) continue
        if (editBlock(i, st.ans)) { assert.ok(i === 4 && st.ans.otherIncome); continue }
        st = { ...st, step: i, editing: true }
      } else {
        const at = st.step === ENTRY ? 0 : st.step
        const v = pick(r, VALUES[at])
        trail.push(`답${at + 1}=${JSON.stringify(v)}`)
        st = answer(st, v)
        if (st.step === 4) assert.notEqual(st.ans.otherIncome, true, `${where}: ④ 있음인데 ⑤를 물음`)
        if (st.step === CONFIRM) checkConfirm(st, where)
      }
    }
  }
  assert.ok(confirms > 10000 && photos > 10000, `조합이 충분히 돌지 않음: 확인 ${confirms}, 사진 ${photos}`)
})

test('질문 도중 앞 칸을 고치면 ⑥으로 건너뛰지 않고 남은 칸을 이어서 묻는다', () => {
  let st: State = { step: 0, ans: {}, editing: false }
  for (const v of [VALUES[0][0], 6_000_000]) st = answer(st, v)
  assert.equal(st.step, 2)
  st = { ...st, step: 0, editing: true } // ③을 묻다가 '내 답'에서 ①을 누름
  st = answer(st, VALUES[0][1])
  assert.equal(st.step, 2, '③부터 다시 물어야 함')
  for (const v of [{ domestic: 0, foreign: 0 }, false, 30_000_000]) st = answer(st, v)
  assert.equal(st.step, CONFIRM)
  checkConfirm(st, '고친 뒤 끝까지')
})

test('③ 한쪽만 모름이면 내 답도 모름, 국내·해외 둘 다 있으면 둘 다 보인다', () => {
  assert.equal(answerText(2, { other: { domestic: null, foreign: 0 } }, S), '모름')
  assert.equal(answerText(2, { other: { domestic: 0, foreign: null } }, S), '모름')
  assert.equal(answerText(2, { other: { domestic: 300_000, foreign: 200_000 } }, S), '국내 300,000원 · 해외·ETF·펀드 200,000원')
  assert.equal(answerText(2, { other: { domestic: 300_000, foreign: null } }, S), '국내 300,000원 · 해외·ETF·펀드 모름')
})

test('용어 질문은 말투가 달라도 같은 용어로 읽는다(직접 쓴 질문 = 누른 질문)', () => {
  const keys = ['배당락', '부채', '공모', '공모가', 'ETF', '자사주 소각', '코스피200', '주식', '주식배당']
  for (const t of ['배당락', '배당락이란?', '배당락 뜻', '배당락이 뭐예요?', '배당락 뜻이 뭐예요', '배당락에 대해 알려줘', '배당락은 뭐야'])
    assert.equal(termKey(t, keys), '배당락', t)
  assert.equal(termKey('부채가 뭐예요?', keys), '부채')
  assert.equal(termKey('etf란', keys), 'ETF')
  assert.equal(termKey('자사주소각이 뭐예요', keys), '자사주 소각')
  assert.equal(termKey('코스피200이란?', keys), '코스피200')
  assert.equal(termKey('공모가 뭐예요?', keys), '공모가') // 용어에 글자 그대로 있으면 조사로 떼지 않는다
  assert.equal(termKey('주식', keys), '주식') // 비슷한 '주식배당'으로 짐작하지 않음
  assert.equal(termKey('배당락 전에 사면 배당 받아요?', keys), null) // 용어 하나만 묻는 말이 아니면 서버 검색에 맡긴다
  assert.equal(termKey('삼성전자 10주', keys), null)
})

test('서버가 고른 기본 금융 용어 답이 같은 용어인지', () => {
  assert.ok(sameTerm('PER(주가수익비율)', 'PER'))
  assert.ok(sameTerm('코스피·코스닥', '코스피'))
  assert.ok(sameTerm('ETF', 'etf'))
  assert.ok(!sameTerm('주식배당', '주식'))
  assert.ok(!sameTerm('배당수익률', '초과수익률'))
})

test('목록에 없어 뺀 종목도 내 답에 보이고 계산 요청에 실린다(보유 종목 수에만 셈)', () => {
  const a: Answers = { holdings: [{ company: '삼성전자', shares: 10 }], outside: ['카카오'] }
  assert.equal(answerText(0, a, S), '삼성전자 10주 · 카카오 (목록에 없어 뺌)')
  assert.equal(answerText(0, { holdings: [], outside: ['카카오'] }, S), '카카오 (목록에 없어 뺌)')
  assert.deepEqual(checkupBody(a).outside, ['카카오'])
  assert.deepEqual(checkupBody({ holdings: [] }).outside, [])
})

test('시작 단계 짧은 말: 시작·거절·도움을 띄어쓰기·문장부호와 상관없이 가르고, 용어 질문만 용어 안내로', async () => {
  const { entryIntent, looksLikeTerm } = await import('../src/checkFlow.ts')
  const words = { start: ['시작', '응', 'ㅇㅇ', 'ok'], decline: ['아니', 'ㄴㄴ'], help: ['도와줘', '모르겠어'] }
  assert.equal(entryIntent('시작!', words), 'start')
  assert.equal(entryIntent('ㅇㅇ', words), 'start')
  assert.equal(entryIntent('OK', words), 'start')
  assert.equal(entryIntent('아니요?', words), null)
  assert.equal(entryIntent('아니.', words), 'decline')
  assert.equal(entryIntent('도와 줘~', words), 'help')
  assert.equal(entryIntent('삼성전자 10주', words), null)
  assert.ok(looksLikeTerm('배당락이란?') && looksLikeTerm('PER 뜻') && looksLikeTerm('ETF 뭐야'))
  assert.ok(!looksLikeTerm('배고파') && !looksLikeTerm('오늘 날씨 어때'))
})
