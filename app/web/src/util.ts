// 여러 화면이 함께 쓰는 작은 도구: 금액·비율 표시, 판정 꼬리표 글자.
import { useEffect, useState } from 'react'
import type { Status } from './api'

/** 원 단위 금액 표시. 1억 원 이상은 억 원(소수 첫째 자리). source/ui/components.py `won`과 같은 규칙. */
export function won(amount: number): string {
  if (Math.abs(amount) >= 100_000_000) {
    return `${(amount / 100_000_000).toLocaleString('ko-KR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}억 원`.replace('.0억', '억')
  }
  return `${amount.toLocaleString('ko-KR')}원`
}

export const pct = (v: number | null | undefined, sign = false) =>
  v == null ? '–' : `${sign && v > 0 ? '+' : ''}${v.toLocaleString('ko-KR', { maximumFractionDigits: 1 })}%`

export type Mood = 'base' | 'happy' | 'sad' | 'curious'
export const moodOf = (s: Status | undefined): Mood => (s === '충족' ? 'happy' : s === '미충족' ? 'sad' : s ? 'curious' : 'base')
export const moaSrc = (m: Mood) => `/moa/moa_${m}.webp`
export const badgeClass = (s: Status) => (s === '충족' ? 'badge--ok' : s === '미충족' ? 'badge--no' : 'badge--hold')

/** 화면이 열릴 때 한 번 불러오는 값 */
export function useLoad<T>(load: () => Promise<T>, deps: unknown[] = []) {
  const [state, set] = useState<{ data?: T; error?: string }>({})
  useEffect(() => {
    let alive = true
    set({})
    load().then(data => alive && set({ data }), (e: Error) => alive && set({ error: e.message }))
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  return state
}
