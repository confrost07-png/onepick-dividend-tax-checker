// '2026 판정'이 어떤 배당·어느 해 세금의 판정인지 펼쳐 보는 칸 (문장은 legal.ts JUDGE_YEAR)
import { JUDGE_YEAR as J } from '../legal'

export default function JudgeYear({ open = false }: { open?: boolean }) {
  return (
    <details className="basis judge-year" open={open}>
      <summary>{J.title}</summary>
      <p>{J.lead}</p>
      <ul>{J.rows.map(([what, when]) => <li key={what}><b>{what}</b> → {when}</li>)}</ul>
      <p>{J.not_this}</p>
      <p>{J.basis}</p>
    </details>
  )
}
