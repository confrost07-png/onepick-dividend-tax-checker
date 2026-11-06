// 자산관리서비스 신청 내역(모형). 로그인한 시연용 고객별로 이 브라우저에만 남긴다(서버로 보내거나 저장하지 않음).
// 마이페이지(/mypage)에서 보고 취소한다. 저장소를 못 쓰는 브라우저(사생활 보호 창 등)에서는 내역이 남지 않는다.
import type { ConsultType, Way } from './bank'

export interface Application {
  no: string; type: ConsultType; typeName: string; way: Way; wayName: string; where: string
  date: string; slot: string; send: boolean; createdAt: string
  status: '신청' | '취소'; canceledAt?: string
}

const key = (who: string) => `onepick.apps.${who}`

export function listApps(who: string): Application[] {
  try {
    const v = JSON.parse(localStorage.getItem(key(who)) || '[]')
    return Array.isArray(v) ? (v as Application[]) : [] // 손으로 바꾼 값 등 목록이 아니면 빈 목록으로 본다
  } catch { return [] }
}

function save(who: string, apps: Application[]): boolean {
  try { localStorage.setItem(key(who), JSON.stringify(apps)); return true } catch { return false }
}

export const addApp = (who: string, app: Application) => save(who, [app, ...listApps(who)])

export function cancelApp(who: string, no: string): Application[] {
  const apps = listApps(who).map(a => (a.no === no && a.status === '신청' ? { ...a, status: '취소' as const, canceledAt: new Date().toISOString() } : a))
  save(who, apps)
  return apps
}

/** 상담 시각이 지났으면 지난 신청(취소할 수 없음). 시간대 글('10:00' 등)이 없으면 그날 끝까지 기다린다 */
export function isPast(a: Application, now = new Date()): boolean {
  const d = new Date(a.date)
  const t = /(\d{1,2}):(\d{2})/.exec(a.slot ?? '')
  if (t) d.setHours(+t[1], +t[2], 0, 0)
  else d.setHours(23, 59, 59)
  return d < now
}
