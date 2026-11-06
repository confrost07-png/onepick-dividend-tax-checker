// A은행(가상) 자산관리서비스와 PB센터. 기획안의 'A은행 종합자산관리서비스'를 화면으로 보여 주는 모형 자료다.
// 실제 은행·지점이 아니며, 예약은 어디에도 보내거나 저장하지 않는다.

export const BANK = 'A은행'
export const SAVED_NOTE = 'A은행은 기획안의 가상 은행이에요. 지점·상담·예약은 모두 모형이라 실제로 신청되지 않아요. 신청 내역은 서버에 보내지 않고 이 브라우저에만 남겨요.'
export const MOCK_NOTE = 'A은행은 기획안의 가상 은행이에요. 지점·상담·예약은 모두 모형이라 실제로 신청되지 않고, 입력한 내용도 저장하지 않아요.'

export type Region = '서울' | '경기·인천' | '충청' | '영남' | '호남' | '강원' | '제주'
export interface Branch { id: string; name: string; region: Region; area: string; days: string[]; video: boolean }

const WEEK = ['월', '화', '수', '목', '금']

// PB센터 14곳. 주소는 시·구까지만 적는다(가상 지점).
export const BRANCHES: Branch[] = [
  { id: 'gangnam', name: '강남', region: '서울', area: '서울 강남구', days: WEEK, video: true },
  { id: 'yeouido', name: '여의도', region: '서울', area: '서울 영등포구', days: WEEK, video: true },
  { id: 'jongno', name: '종로', region: '서울', area: '서울 종로구', days: ['월', '수', '금'], video: true },
  { id: 'suwon', name: '수원', region: '경기·인천', area: '경기 수원시', days: ['화', '목'], video: true },
  { id: 'bundang', name: '분당', region: '경기·인천', area: '경기 성남시', days: ['월', '화', '목'], video: true },
  { id: 'songdo', name: '인천송도', region: '경기·인천', area: '인천 연수구', days: ['수', '금'], video: false },
  { id: 'daejeon', name: '대전충청', region: '충청', area: '대전 서구', days: ['월', '수', '금'], video: true },
  { id: 'daegu', name: '대구경북', region: '영남', area: '대구 수성구', days: ['화', '수', '목'], video: true },
  { id: 'centum', name: '부산센텀', region: '영남', area: '부산 해운대구', days: WEEK, video: true },
  { id: 'ulsan', name: '울산', region: '영남', area: '울산 남구', days: ['화', '금'], video: false },
  { id: 'gwangju', name: '광주', region: '호남', area: '광주 서구', days: ['월', '목'], video: true },
  { id: 'jeonju', name: '전주', region: '호남', area: '전북 전주시', days: ['수'], video: false },
  { id: 'wonju', name: '원주', region: '강원', area: '강원 원주시', days: ['목'], video: false },
  { id: 'jeju', name: '제주', region: '제주', area: '제주 제주시', days: ['화', '금'], video: true },
]
export const REGIONS: Region[] = ['서울', '경기·인천', '충청', '영남', '호남', '강원', '제주']

export type ConsultType = 'separate' | 'filing' | 'general'
export const CONSULT_TYPES: { id: ConsultType; name: string; line: string }[] = [
  { id: 'separate', name: '고배당 분리과세 상담', line: '분리과세를 신청할지, 내 소득에서 무엇이 달라지는지 세무 전문가와 함께 봐요.' },
  { id: 'filing', name: '금융소득 종합과세 신고대행', line: '5월 종합소득세 확정신고를 제휴 세무법인이 대신 해 드려요. 분리과세신청서 제출도 함께 도와요.' },
  { id: 'general', name: '그 밖의 세무 상담', line: '증여·상속처럼 배당 말고 다른 세금이 궁금할 때예요.' },
]

export type Way = 'visit' | 'phone' | 'video'
export const WAYS: { id: Way; name: string; line: string }[] = [
  { id: 'visit', name: 'PB센터 방문', line: '가까운 PB센터에서 세무 전문가를 만나요.' },
  { id: 'phone', name: '전화 상담', line: '정한 시간에 세무 전문가가 전화해요.' },
  { id: 'video', name: '화상 상담', line: '화상으로 화면을 같이 보며 상담해요(화상 가능 지점 연결).' },
]

export const SLOTS = ['10:00', '11:00', '13:30', '14:30', '15:30']

/** 평일 날짜 목록 (오늘 다음 날부터) */
export function nextBusinessDays(n: number, from = new Date()): Date[] {
  const out: Date[] = []
  const d = new Date(from.getFullYear(), from.getMonth(), from.getDate())
  while (out.length < n) {
    d.setDate(d.getDate() + 1)
    if (d.getDay() !== 0 && d.getDay() !== 6) out.push(new Date(d))
  }
  return out
}
export const dayName = (d: Date) => '일월화수목금토'[d.getDay()]
export const dateText = (d: Date) => `${d.getMonth() + 1}월 ${d.getDate()}일(${dayName(d)})`

/** 모형: 이미 찬 시간처럼 보이게 지점·날짜·시간으로 정해진 값을 만든다(날마다 같은 결과) */
export function isTaken(branch: string, d: Date, slot: string): boolean {
  const key = `${branch}${d.getMonth()}${d.getDate()}${slot}`
  let h = 0
  for (const ch of key) h = (h * 31 + ch.charCodeAt(0)) % 1000
  return h % 3 === 0
}

/** 모형 예약 번호 (화면에서만 만들고 어디에도 저장하지 않음) */
export function mockNumber(): string {
  return `A-${Math.random().toString(36).slice(2, 6).toUpperCase()}-${Math.floor(1000 + Math.random() * 9000)}`
}
