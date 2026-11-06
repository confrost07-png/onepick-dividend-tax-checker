// 1장 법 토너먼트 그림: 동전 638개가 요건 세 개를 지나는 움직임을 그린다(그리기는 tournamentEngine).
import { useEffect, useRef } from 'react'
import type { Funnel } from '../api'
import { mountTournament } from './tournamentEngine'

export default function Tournament({ funnel, autoplay = 'none', compact = false }: { funnel: Funnel; autoplay?: 'visible' | 'none'; compact?: boolean }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const still = new URLSearchParams(location.search).has('still') || matchMedia('(prefers-reduced-motion: reduce)').matches
    return mountTournament(ref.current!, funnel, { autoplay, still })
  }, [funnel, autoplay])
  return (
    <div
      ref={ref}
      className={`tour${compact ? ' tour--compact' : ''}`}
      role="group"
      aria-label={`법 토너먼트: ${funnel.total}곳 중 충족 ${funnel.ga + funnel.na + funnel.na_deficit}, 미충족 ${funnel.fail2 + funnel.fail3}, 판정 보류 ${funnel.hold_missing + funnel.hold_zero}`}
    />
  )
}
