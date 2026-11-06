// 모아의 금융 상식 칼럼: 원픽 분석에 나오는 어려운 금융 용어와 개념을 초등학생도 알 수 있게 푼 글.
// 원픽 팀 해설 초안(AI 도움을 받아 씀, 팀 검토 전). 문단마다 [조문]·[팀 해석]·[데이터]·[쉬운 설명]을 붙인다.
// 세법 해석·투자 권유를 하지 않는다. {{용어}}는 용어 사전으로 이어지고, {이름} 자리에는 API 값(판정 흐름·분석)을 넣는다.
// 그림 도구(toy)에 나오는 숫자는 읽는 사람이 직접 움직여 보는 예시다. 세율 계단·달리기 시합·점 찍어 보기는 실제 계산·실제 사례(API)를 쓴다.
import type { Mood } from './util'
import * as u1 from './columns/unit1'
import * as u2 from './columns/unit2'
import * as u3 from './columns/unit3'
import * as u4 from './columns/unit4'
import * as u5 from './columns/unit5'
import * as u6 from './columns/unit6'
import * as u7 from './columns/unit7'
import * as u8 from './columns/unit8'
import * as u9 from './columns/unit9'
import * as u10 from './columns/unit10'
import * as u11 from './columns/unit11'
import * as u12 from './columns/unit12'
import * as u13 from './columns/unit13'

export type Source = '조문' | '팀 해석' | '데이터' | '쉬운 설명'
export type Toy = 'pizza' | 'stairs' | 'gates' | 'balance' | 'wallet' | 'race' | 'lineup' | 'coins' | 'stockbond' | 'votes' | 'taxhelper' | 'wealth'
  | 'fincome' | 'withhold' | 'kinds' | 'grossup' | 'savings' | 'fx' | 'account' | 'basket'
  | 'yields' | 'divcal' | 'recordday' | 'payback' | 'taxflow'
  | 'index' | 'knockin' | 'eld' | 'etn' | 'meeting' | 'splitter' | 'merger'
  | 'ipo' | 'delistpath' | 'waterfall' | 'capital' | 'ledger' | 'disclosure' | 'ratemachine' | 'brakes' | 'isabox' | 'pension'
  | 'deposit' | 'shelf'
export type Block =
  | { t: 'h'; text: string }
  | { t: 'box'; kind: 'myth' | 'sum' | 'tip'; title: string; items: string[] }
  | { t: 'p'; text: string; src?: Source }
  | { t: 'say'; who: 'moa' | 'me'; text: string; mood?: Mood }
  | { t: 'quiz'; q: string; options: string[]; answer: number; why: string }
  | { t: 'toy'; toy: Toy }
  | { t: 'link'; to: string; text: string }

export interface Term { easy: string; like?: string }
export interface Episode { id: string; no: number; title: string; hook: string; mood: Mood; terms: string[]; blocks: Block[]; laws: string[]; toyName?: string; qs?: string[] }

export const COLUMN_NOTE = '원픽 팀이 쓴 쉬운 풀이 초안이에요(AI 도움을 받아 썼고, 팀 검토 전이에요). 투자 권유나 세무 조언이 아니에요. 그림 도구의 숫자는 직접 움직여 보는 예시예요.'

/** 용어 사전: 어려운 말 → 초등학생도 알 수 있는 말 */
const BASE_GLOSSARY: Record<string, Term> = {
  '주식': { easy: '회사를 아주 잘게 나눈 조각이에요. 주식을 가지면 그 회사의 작은 주인이 돼요.', like: '반 친구들이 돈을 모아 가게를 열면, 낸 돈만큼 가게 주인 몫을 나눠 갖는 것' },
  '주주': { easy: '주식을 가진 사람이에요. 회사의 작은 주인이에요.' },
  '채권': { easy: '나라·지방자치단체·회사 등이 돈을 빌리면서 "언제까지 이자를 붙여 갚을게요"라고 써 준 약속 증서예요. 나라가 내면 국채, 지방자치단체가 내면 지방채, 회사가 내면 회사채(사채)라고 해요.', like: '친구에게 돈을 빌려주고 받은 차용증' },
  '이자': { easy: '돈을 빌려준 대가로 받는 돈이에요. 채권은 정해진 이자를 받아요.' },
  '의결권': { easy: '주주총회에서 회사 일을 정할 때 던지는 표예요. 보통 1주에 1표예요.' },
  '배당권': { easy: '회사가 배당을 하면, 가진 주식 수만큼 나눠 받을 권리예요.' },
  '주주총회': { easy: '주주들이 모여 배당금, 이사 선임 같은 회사의 큰일을 정하는 회의예요.', like: '반 회의에서 다수결로 정하기' },
  '우선주': { easy: '보통 의결권이 없는 대신 배당을 먼저 받거나 더 받기로 한 주식이에요. 보통 주식은 보통주라고 해요.' },
  '배당': { easy: '회사가 번 돈의 일부를 주인(주주)들에게 나눠 주는 돈이에요.', like: '가게가 장사를 잘해서 남은 돈을 주인들이 나눠 갖는 것' },
  '순이익': { easy: '회사가 1년 동안 번 돈에서 쓴 돈과 세금을 모두 빼고 남은 돈이에요.', like: '용돈에서 간식값을 다 쓰고 남은 돈' },
  '배당성향': { easy: '순이익 중에서 배당으로 나눠 준 비율이에요. 100원 벌어 30원 나눠 주면 30%예요.' },
  '이익배당금액': { easy: '그 해에 돈(현금)으로 나눠 준 배당을 모두 더한 금액이에요. 주식으로 준 배당은 넣지 않아요.' },
  '사업연도': { easy: '회사가 장부를 정리하는 1년이에요. 보통 1월부터 12월까지예요.' },
  '상장': { easy: '회사 주식을 증권거래소에서 누구나 사고팔 수 있게 이름을 올리는 거예요.', like: '큰 시장에 가게 자리를 얻는 것' },
  '코넥스': { easy: '아직 작은 회사들이 먼저 이름을 올리는 작은 시장이에요. 이번 제도에서는 빠져요.' },
  '공시': { easy: '회사가 중요한 일을 모두가 볼 수 있게 공개 게시판에 알리는 거예요.', like: '학교 알림장에 올리는 공지' },
  '종합과세': { easy: '여러 가지 소득을 한 주머니에 모두 합쳐서 세금을 매기는 방식이에요. 주머니가 무거울수록 세율이 올라가요.' },
  '분리과세': { easy: '어떤 소득은 큰 주머니에 넣지 않고 따로 작은 주머니에 담아 정해진 세율로 세금을 매기는 방식이에요.' },
  '누진세율': { easy: '많이 벌수록 넘친 부분에 더 높은 세율이 붙는 계단 같은 세율이에요.' },
  '연결재무제표': { easy: '엄마 회사(모회사)와 자녀 회사(자회사)의 장부를 한 가족처럼 합쳐 만든 장부예요.' },
  '지배주주 순이익': { easy: '가족 회사 전체 이익 중에서 엄마 회사 주주 몫만 떼어 낸 이익이에요.' },
  '적자': { easy: '번 돈보다 쓴 돈이 많아 순이익이 0원보다 작은 거예요.' },
  '부채': { easy: '회사가 남에게 빌린 돈, 갚아야 할 돈이에요.', like: '친구한테 빌린 돈' },
  '자본': { easy: '빌린 돈이 아니라 회사가 스스로 가진 돈이에요. 주인들이 낸 돈과 모아 둔 이익이에요.' },
  '영업현금흐름': { easy: '회사가 장사해서 실제로 손에 들어온 현금이에요.' },
  '설비투자': { easy: '공장이나 기계처럼 앞으로 장사하려고 꼭 써야 하는 돈이에요.' },
  '잉여현금흐름': { easy: '들어온 현금에서 꼭 써야 할 돈(설비투자)을 빼고 남은 돈이에요. 이 돈으로 배당을 줄 수 있어요.' },
  '재무 여력': { easy: '남은 돈(잉여현금흐름)이 줘야 할 배당의 몇 배인지예요. 1배가 안 되면 남은 돈만으로는 모자라요.' },
  '수익률': { easy: '처음 돈에 비해 얼마나 늘었는지를 %로 나타낸 거예요. 100원이 110원이 되면 10%예요.' },
  '시장지수': { easy: '시장에 있는 여러 회사 주가를 한데 모아 만든 평균 점수예요. KOSPI, KOSDAQ 같은 거예요.', like: '반 평균 점수' },
  '초과수익률': { easy: '내 주식 수익률에서 시장 수익률을 뺀 거예요. 시장보다 얼마나 더 잘 달렸는지예요.', like: '내 점수 − 반 평균 점수' },
  '평균': { easy: '모두 더해서 개수로 나눈 값이에요. 아주 큰 값 몇 개가 끼면 확 바뀌어요.' },
  '중앙값': { easy: '작은 것부터 줄 세웠을 때 딱 가운데 있는 값이에요. 아주 큰 값이 끼어도 잘 안 바뀌어요.' },
  '가운데 절반 범위': { easy: '줄 세운 뒤 앞 4분의 1과 뒤 4분의 1을 빼고 남은 가운데 절반이 있는 범위예요(25~75%).' },
  '표본': { easy: '전부를 다 볼 수 없을 때 살펴보는 일부예요. 많을수록 믿을 만해요.' },
  'p값': { easy: '"사실은 아무 차이가 없는데 우연히 이만큼 나올 가능성"이에요. 아주 작으면 우연이라 보기 어려워요.' },
  '세무사': { easy: '세금 신고를 대신 해 주고, 세금 문제를 상담해 주는 국가 자격을 가진 전문가예요.' },
  '신고 대리': { easy: '내 대신 세무사가 세금 신고서를 만들어 내 주는 거예요. 은행 서비스에서는 신고대행이라고도 불러요.' },
  '종합소득세 확정신고': { easy: '1년 동안 번 소득을 모아 다음 해 5월에 세금을 정산해 신고하는 거예요.' },
  '자산관리서비스': { easy: '은행이 고객의 예금·투자·세금·은퇴 준비를 한꺼번에 살펴 주는 서비스예요.', like: '돈 관리 주치의' },
  '금융소득': { easy: '이자소득과 배당소득을 합친 말이에요. 돈이 돈을 벌어 온 소득이에요.' },
  '이자소득': { easy: '예금이나 채권처럼 돈을 빌려주고 받은 이자예요.' },
  '배당소득': { easy: '주식을 가져서 받은 배당이에요. 법에서는 세금을 매기는 배당을 이렇게 불러요.' },
  '원천징수': { easy: '돈을 줄 때 세금을 미리 떼고 주는 거예요. 배당이나 이자를 받을 때 이미 세금이 빠져 있어요.', like: '급식비를 용돈에서 미리 떼고 받는 것' },
  '원천징수영수증': { easy: '회사나 은행이 "이만큼 주고 세금은 이만큼 미리 뗐어요"라고 적어 주는 종이예요. 근로소득 원천징수영수증에 과세표준이 적혀 있어요.' },
  '과세표준': { easy: '세금을 매기는 기준이 되는 금액이에요. 번 돈에서 빼 주는 것(공제)을 빼고 남은 금액이에요.' },
  '소득공제': { easy: '세금을 매기기 전에 번 돈에서 빼 주는 금액이에요. 많이 빼 줄수록 과세표준이 작아져요.' },
  '근로소득': { easy: '회사에 다니며 받은 월급과 상여금이에요.' },
  '사업소득': { easy: '가게나 프리랜서 일처럼 스스로 사업해서 번 돈이에요.' },
  '연금소득': { easy: '나이가 들어 받는 연금이에요. 국민연금, 개인연금 같은 거예요.' },
  '기타소득': { easy: '강연료, 원고료, 상금처럼 가끔 생기는 소득이에요.' },
  '배당가산': { easy: '회사가 이미 법인세를 낸 이익으로 준 배당이라, 세금을 두 번 매기지 않도록 배당에 일정 금액을 더해 계산한 뒤 그만큼 세금에서 빼 주는 방법이에요. 그로스업이라고도 해요.' },
  '배당세액공제': { easy: '배당가산으로 더한 만큼을 계산이 끝난 세금에서 다시 빼 주는 거예요.' },
  'ETF': { easy: '여러 주식이나 채권을 한 바구니에 담아 주식처럼 사고파는 상품이에요.' },
  '분배금': { easy: 'ETF나 펀드가 바구니에서 생긴 이익을 나눠 주는 돈이에요. 회사가 주는 배당과는 이름도, 세금 규칙도 달라요.' },
  '금리': { easy: '돈을 빌리고 빌려주는 값이에요. 1년에 몇 %의 이자를 붙이는지로 나타내요.' },
  '기준금리': { easy: '한국은행이 정하는 나라의 대표 금리예요. 예금·대출 금리가 이것을 따라 움직이는 경향이 있어요.' },
  '복리': { easy: '이자에도 다시 이자가 붙는 방식이에요. 오래 둘수록 눈덩이처럼 커져요.' },
  '환율': { easy: '우리 돈과 다른 나라 돈을 바꾸는 비율이에요. 보통 "1달러 = 1,400원"처럼 다른 나라 돈을 기준으로 적고, 일본 엔화는 100엔이 우리 돈 얼마인지로 적어요.' },
  '원화 약세': { easy: '같은 1달러를 사려면 원화가 더 많이 필요해진 거예요(환율이 올라감). 수입품은 비싸지고, 수출 기업은 원화로 더 많이 받아요.' },
  '경상수지': { easy: '나라가 다른 나라와 물건·서비스·이자·배당을 주고받고 남은 돈이에요. 나라의 1년 가계부예요.' },
  '상품수지': { easy: '수출한 물건값에서 수입한 물건값을 뺀 거예요.' },
  '서비스수지': { easy: '여행, 운송, 지식재산권처럼 눈에 안 보이는 서비스를 팔고 산 돈의 차이예요.' },
  '본원소득수지': { easy: '해외에 투자해서 받은 배당·이자, 해외에서 번 월급 등에서 우리가 내준 것을 뺀 거예요.' },
  '물가': { easy: '여러 물건과 서비스의 값을 모아 본 평균 가격 수준이에요.' },
  '인플레이션': { easy: '물가가 계속 오르는 거예요. 같은 돈으로 살 수 있는 물건이 줄어요.' },
  '실질수익률': { easy: '수익률에서 물가 오른 만큼을 뺀 진짜 늘어난 정도예요.' },
  '주당배당금': { easy: '주식 1주에 주는 배당금이에요. 내가 받는 배당 = 주당배당금 × 가진 주식 수예요.' },
  '배당수익률': { easy: '주가에 비해 1년 배당을 얼마나 주는지예요. 주당배당금 ÷ 주가예요.' },
  '배당기준일': { easy: '이날 주주 명단에 이름이 있어야 배당을 받는 날이에요.' },
  '배당락일': { easy: '이날부터 사면 이번 배당은 못 받는 날이에요. 기준일 바로 전 거래일이에요.' },
  '권리락': { easy: '증자로 새 주식을 받을 권리가 빠지는 날이에요. 그만큼 주가 기준을 낮춰 맞춰요.' },
  '현금배당': { easy: '배당은 주는 방식에 따라 현금배당, 주식배당 등으로 나뉘어요. 그중 배당을 현금으로 주는 거예요. 보통 증권 계좌로 들어와요.' },
  '주식배당': { easy: '배당을 돈 대신 새 주식으로 주는 거예요.' },
  '결산배당': { easy: '1년 장사를 마감하고 주는 배당이에요. 보통 다음 해 봄에 받아요.' },
  '중간배당': { easy: '1년 중간(보통 6월 말 기준)에 미리 주는 배당이에요.' },
  '분기배당': { easy: '3개월마다 주는 배당이에요. 1년에 네 번까지 받을 수 있어요.' },
  '누적적 배당': { easy: '우선주가 못 받은 배당을 다음 해에 쌓아서 받는 방식이에요. 못 받은 건 사라지면 비누적적이에요.' },
  '이익잉여금': { easy: '회사가 그동안 벌어서 나눠 주지 않고 쌓아 둔 이익이에요. 적자인 해에도 이 범위 안에서 배당할 수 있어요.' },
  '액면분할': { easy: '주식 한 주를 여러 주로 쪼개는 거예요. 피자를 더 잘게 자르는 것처럼 회사 크기는 그대로예요.' },
  '증자': { easy: '회사가 주식을 새로 더 찍어 내는 거예요. 돈을 받고 팔면 유상증자, 공짜로 나눠 주면 무상증자예요.' },
  '주주환원': { easy: '회사가 번 돈을 주주에게 돌려주는 일이에요. 배당을 주거나, 자기 주식을 사서 없애는(소각) 방법이 있어요.' },
  '자사주 소각': { easy: '회사가 자기 주식을 사서 없애는 거예요. 주식 수가 줄어 남은 주식 한 주의 몫이 커져요.' },
  '밸류업': { easy: '회사 가치를 높이겠다는 계획이에요. 기업가치 제고 계획이라는 이름으로 공시해요.' },
  '세액공제': { easy: '계산이 끝난 세금에서 바로 빼 주는 금액이에요.' },
  '비과세': { easy: '처음부터 세금을 매기지 않는 소득이에요.' },
  '양도소득': { easy: '주식이나 집을 판 값에서 산 값을 빼고 남은 이익이에요.' },
  '감액배당': { easy: '번 돈이 아니라 회사가 쌓아 둔 자본준비금을 줄여서 나눠 주는 배당이에요.' },
  '자본준비금': { easy: '주식을 팔 때 액면가보다 더 받은 돈처럼, 회사가 따로 쌓아 둔 돈이에요.' },
}

// 칼럼은 순서대로 읽는 학습 길이다. 단원별로 묶는다.
export const UNITS = [
  { no: 1, name: '주식의 기초', line: '회사의 주인이 된다는 것', color: '#3D6BFF', tint: '#EEF2FF', ids: ['stockbond', 'rights', 'dividend', 'decide'] },
  { no: 2, name: '배당 더 알기', line: '종류·받는 날·숫자·주주환원', color: '#E26B3A', tint: '#FFF0E8', ids: ['dkinds', 'recordday', 'yieldratio', 'payback'] },
  { no: 3, name: '내 소득과 세금', line: '점검에서 묻는 말 이해하기', color: '#C2410C', tint: '#FDEBDD', ids: ['fincome', 'withhold', 'kinds', 'deduct', 'grossup', 'pocket'] },
  { no: 4, name: '고배당 분리과세', line: '어떤 회사 배당이 대상일까', color: '#E0A500', tint: '#FFF6DB', ids: ['gates', 'debt', 'reduction'] },
  { no: 5, name: '회사 읽는 법', line: '재무제표와 공시', color: '#4C7A2E', tint: '#EEF5E8', ids: ['statements', 'disclosure'] },
  { no: 6, name: '숫자 읽기', line: '그래프 속 숫자가 말하는 것', color: '#19B36B', tint: '#E8F7EF', ids: ['cash', 'race', 'median', 'chance'] },
  { no: 7, name: '경제 큰 그림', line: '금리·기준금리·환율·나라 가계부·물가', color: '#0E9FB5', tint: '#E4F6F8', ids: ['rate', 'baserate', 'fx', 'account', 'inflation'] },
  { no: 8, name: '투자상품 알기', line: '지수·시장 브레이크·ELS·ELD·ETN', color: '#D9468A', tint: '#FDECF4', ids: ['index', 'brakes', 'els', 'eld', 'etn'] },
  { no: 9, name: '회사의 큰일', line: '주주총회·분할·증자·감자·인수합병', color: '#8A6A3D', tint: '#F6EFE4', ids: ['owners', 'split', 'capital', 'mna'] },
  { no: 10, name: '회사의 시작과 끝', line: '상장·청약·상장폐지·부도·파산', color: '#5B5F97', tint: '#ECEDF7', ids: ['ipo', 'delist', 'distress'] },
  { no: 11, name: '세금 혜택 계좌', line: 'ISA·IRP와 고배당 분리과세', color: '#0F766E', tint: '#E6F4F1', ids: ['isa', 'irp'] },
  { no: 12, name: '도움받기', line: '누가 어떻게 도와줄까', color: '#7B61FF', tint: '#F1EEFF', ids: ['whyno', 'taxpro', 'wealth'] },
  { no: 13, name: '돈 맡기는 곳', line: '예금·적금·CMA·IMA', color: '#2563EB', tint: '#E8F0FE', ids: ['deposit', 'cmaima'] },
]
const UNIT_FILES = [u1, u2, u3, u4, u5, u6, u7, u8, u9, u10, u11, u12, u13]
const RAW_EPISODES: Episode[] = UNIT_FILES.flatMap(u => u.EPISODES)
/** 용어 사전: 기본 용어 + 단원 파일이 더한 용어 */
export const GLOSSARY: Record<string, Term> = Object.assign({}, BASE_GLOSSARY, ...UNIT_FILES.map(u => u.TERMS))
// 첫 화면은 단원 13개를 큰 묶음 4개로 보여 준다. 한 번에 한 묶음만 펼친다.
export const THEMES = [
  { key: 'basic', name: '배당과 주식 기초', line: '주식과 배당이 무엇인지', color: '#3D6BFF', tint: '#EEF2FF', units: [1, 2] },
  { key: 'tax', name: '내 세금과 분리과세', line: '점검에서 묻는 말과 도움받는 길', color: '#C2410C', tint: '#FDEBDD', units: [3, 4, 11, 12] },
  { key: 'company', name: '회사와 숫자 읽기', line: '재무제표·공시·그래프·회사의 큰일', color: '#4C7A2E', tint: '#EEF5E8', units: [5, 6, 9, 10] },
  { key: 'economy', name: '경제와 투자상품', line: '금리·환율·물가, 예금·CMA·IMA와 지수·ELS·ETN', color: '#0E9FB5', tint: '#E4F6F8', units: [7, 13, 8] },
]
export type Theme = (typeof THEMES)[number]
export const themeUnits = (t: Theme) => t.units.map(n => UNITS.find(u => u.no === n)!)
export const themeOf = (id: string) => THEMES.find(t => themeUnits(t).some(u => u.ids.includes(id)))!
/** 처음 온 사람에게 먼저 권하는 글: 원픽 점검에 바로 필요한 것 */
export const START_HERE = ['dividend', 'fincome', 'withhold', 'gates', 'pocket']
/** 읽는 순서: 묶음 순서 → 단원 순서. 글 번호도 이 순서대로 붙인다 */
export const READ_ORDER = THEMES.flatMap(t => themeUnits(t).flatMap(u => u.ids))
export const EPISODES: Episode[] = READ_ORDER.map((id, i) => ({ ...RAW_EPISODES.find(e => e.id === id)!, no: i + 1 }))
