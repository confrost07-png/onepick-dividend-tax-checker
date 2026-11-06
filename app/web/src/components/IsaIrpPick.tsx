// 점검 결과(금융소득 2천만 원 이하)에 붙는 ISA·IRP 구간 버튼. 총급여 구간을 고르면 /api/isa-irp(core.isa_irp)로
// 내 이자·배당 기준 ISA 세금과 IRP 세액공제를 계산해 보여 준다. 추천이 아니라 계산만 하고, 제약을 함께 적는다.
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import type { IsaIrp } from '../api'
import { won } from '../util'

const IRP_DEMO = 9_000_000 // 연금저축 합산 세액공제 한도만큼 넣는다고 볼 때
const BRACKETS = [
  { key: 'low', label: '총급여 5,000만 원 이하' },
  { key: 'mid', label: '총급여 5,000만~5,500만 원' },
  { key: 'high', label: '총급여 5,500만 원 초과' },
  { key: 'biz_low', label: '종합소득 3,800만 원 이하' },
  { key: 'biz_mid', label: '종합소득 3,800만~4,500만 원' },
  { key: 'biz_high', label: '종합소득 4,500만 원 초과' },
  { key: '', label: '잘 모르겠어요' },
]
const pct = (p: number) => `${(p / 10).toLocaleString('ko-KR', { maximumFractionDigits: 1 })}%`

/** preset: 원천징수영수증 사진의 ㉑ 총급여로 고른 구간. 있으면 그 구간을 먼저 골라 보여 주고, 고객이 다른 구간을 눌러 바꿀 수 있다 */
export default function IsaIrpPick({ fin, preset }: { fin: number; preset?: string }) {
  const [pick, setPick] = useState<string | null>(null)
  const [g, setG] = useState<IsaIrp>()
  const [error, setError] = useState('')

  const choose = (key: string) => {
    setPick(key); setError('')
    api.isaIrp({ bracket: key || null, profit: fin, irp: IRP_DEMO, pension_saving: 0 }).then(setG, (e: Error) => setError(e.message))
  }
  useEffect(() => { if (preset) choose(preset) }, [preset]) // eslint-disable-line react-hooks/exhaustive-deps
  const isaTax = g && (g.chosen?.isa_type === '서민형' ? g.isa.low_income : g.isa.general)

  return (
    <div className="ii-pick">
      <p className="ii-pick-lead">💡 금융소득이 2천만 원 이하라 분리과세로는 세금이 달라지지 않아요. 대신 ISA·IRP로는 달라질 수 있어요. <b>소득이 어느 구간인가요?</b> 근로소득만 있으면 총급여, 사업소득 등이 있으면 종합소득금액으로 골라 주세요.</p>
      <div className="chips">
        {BRACKETS.map(b => (
          <button key={b.key || 'unknown'} type="button" className={`chip${pick === b.key ? ' chip--on' : ''}`} aria-pressed={pick === b.key} onClick={() => choose(b.key)}>{b.label}</button>
        ))}
      </div>
      {preset && pick === preset && <p className="small ii-preset">🧾 원천징수영수증 ㉑ 총급여 기준으로 골랐어요. 다르면 다른 구간을 눌러 주세요.</p>}
      {error && <p className="small" style={{ color: 'var(--no)' }}>{error}</p>}
      {g && pick !== null && (
        <div className="ii-pick-out">
          <div>
            <b>ISA {g.chosen ? `${g.chosen.isa_type} · ${(g.chosen.isa_free / 10_000).toLocaleString('ko-KR')}만 원까지 비과세` : '· 일반형 200만 원, 서민형 400만 원까지 비과세'}</b>
            <span>
              예를 들어 지금 1년 이자·배당 {won(fin)}만큼을 ISA 안에서 벌고 계좌를 닫으면, 보통 계좌는 세금 {won(g.isa.normal)},{' '}
              {g.chosen ? `ISA ${g.chosen.isa_type}은 ${won(isaTax ?? 0)}` : `ISA 일반형 ${won(g.isa.general)} · 서민형 ${won(g.isa.low_income)}`}이에요.
              비과세 한도는 해마다가 아니라 계좌를 닫을 때 모든 순이익에 한 번 적용돼요.
            </span>
            <em>3년은 꼭 채워야 해요 · 1년 2,000만 원, 모두 1억 원까지 넣을 수 있어요 · 직전 3년 안에 금융소득종합과세 대상이었다면 가입할 수 없어요</em>
          </div>
          <div>
            <b>IRP · 넣은 돈의 {g.irp.map(r => pct(r.rate_permil)).join(' 또는 ')} 세액공제</b>
            <span>1년에 900만 원을 넣으면 연말정산 때 세금에서 최대 {g.irp.map(r => won(r.credit)).join(' 또는 ')}까지 빼 줘요(참고 계산, 확정 환급액 아님). 낼 세금보다 많이 빼 주지는 않아요.</span>
            <em>55세 이후 연금으로 받아야 해요 · 중간에 깨면 16.5%를 내요</em>
          </div>
          <p className="small">{g.notice} <Link to={`/isa-irp${pick ? `?b=${pick}` : ''}`}>제도별 비교에서 금액을 바꿔 계산해 보기 →</Link></p>
        </div>
      )}
    </div>
  )
}
