// FastAPI(source/api/main.py)가 돌려주는 값의 모양과 부르는 함수

export type Status = '충족' | '미충족' | '판정 보류'

export interface Link { url: string; label: string; note: string }

export interface Stock {
  name: string; code: string; status: Status; route: string | null; reasons: string[]
  deemed_payout: number | null; listed_2025: boolean
  b2024: number | null; b2025: number | null; d2024: number | null; d2025: number | null
  b_growth_pct: number | null; d_growth_pct: number | null; payout_pct: number | null
  need_2027: number | null; need_status: string | null; ratio_to_2025_pct: number | null
  sources: Link[]
}

export interface Funnel {
  total: number; hold_missing: number; fail2: number; ga: number; na: number
  na_deficit: number; hold_zero: number; fail3: number
}

// [일, 사례 수, 가운데 값, 25%, 75%]
export type CurvePoint = [number, number, number, number, number]

export interface Analysis {
  retro: [number, number, number, number, number][] // 사업연도, 충족, 다음 해 판정 가능, 다음 해 탈락, 탈락률(%)
  drop_reasons: [string, number][]
  payout: [number, number][]
  growth: [number, number][]
  min_ratio: [string, number][]
  notes: Record<string, number>
  event: { basis: string; curves: Record<string, CurvePoint[]> }
  holder: { table: HolderRow[]; notes: { n_holder: number; n_pct: number; n_compared: number; kinds: Record<string, number> }; near_pp: number } | null
  macro: Macro | null
  behavior: Behavior | null
  capacity: { bins: [string, number][]; n: number; median: number | null; other: Record<string, number> }
  trust: {
    source_verify: Record<string, number>; dart_verify: Record<string, number>; review: Record<string, number>
    policy_filings: number; policy_documents: number; ocr_pages: number; price_rows: number; event_cases: number; companies: number
    control: ControlTrust | null
    holder: { rows: number; companies: number; pct: number } // 최대주주·특수관계인 지분 (OpenDART 최대주주 현황)
    totals: { companies: number; fin_rows: number; price_rows: number; price_companies: number; holder_rows: number; source_rows: number; source_tables: number; result_rows: number; result_tables: number } | null // 638곳 + 대조군 합계, 원천·결과 표 전체 행
    resolution: Resolution | null
  }
  control: Control | null
}

// 코드 대조에서 다르거나 못 찾은 칸이 팀 검토·원문 대조로 어떻게 처리됐는지 (source/scripts/verify_resolution.py)
export interface Resolution {
  built: string
  source_verify: { open: number; settled: number; detail: Record<string, number> }
  dart_verify: { open: number; settled: number; detail: Record<string, number> }
}

// 대조군 데이터: 규모와 겹치는 회사로 우리 값과 맞춰 본 결과
export interface ControlHolder {
  industry: string; group: string; n: number; median: number; p25: number; p75: number; person_pct: number; bins: [string, number][]
}

export interface ControlTrust {
  companies: number; overlap: number; fin_rows: number; price_companies: number; price_rows: number
  holder_rows: number; holder_companies: number
  overlap_diff: number; overlap_unexplained: number; corrected: number
}

// 우리 638곳 vs 대조군 (source/scripts/analyze_panel.py → partner.analysis_result). 집단 이름은 '우리 638사' / '대조군'
export interface Control {
  industry_2025: [string, string, number, number | null, number | null, number | null, number | null, number | null][] // 업종, 집단, 회사, 배당한 비율, 배당성향, ROE, 부채비율, 자본(억)
  trend: [number, number | null, number | null, number | null, number | null][] // 연도, 우리 배당한 비율, 우리 배당성향, 대조군 배당한 비율, 대조군 배당성향
  increase: [number, number, number | null, number, number | null][] // 연도(전년→그해), 우리 회사, 우리 10%↑ 비율, 대조군 회사, 대조군 10%↑ 비율
  simulation: { approx_n: number; approx_agree: number; control_n: number; met: number; reit_excluded: number; eligible: number; not_met: number; hold: number }
  car: [number, string, string, number, number | null, number | null, number | null][] // 창, 증가/유지·감소, 집단, 사례, 평균, 중앙값, p
  returns: (number | null)[][] // 연도, 우리 회사, 우리 수익률, 우리 초과, 대조군 회사, 대조군 수익률, 대조군 초과, 코스피, 코스닥
  returns_end: string | null
  sample: [string, string | null, number, number][]
  holder?: ControlHolder[] // 2025 최대주주+특수관계인 보통주 지분율 (같은 업종끼리)
  built_at: string
}

// 회사 행동 분석 (core.core_behavior_*): exposure = 금리·환율 노출도, policy = 분리과세 이중차분
export interface BehaviorFit {
  name: string; role: 'primary' | 'robust' | 'placebo'; coef: number | null; low: number | null; high: number | null
  p_cluster: number | null; p_perm: number | null; p_holm: number | null; n: number; n_firms: number; n_treated: number | null
}
export type BehaviorRow = [string, number, number | null, number | null, number | null, number | null] // 무리, 연도(없으면 0), 값, 아래, 위, 회사·연도 수
export interface Behavior { fits: Record<string, BehaviorFit[]>; series: Record<string, Record<string, BehaviorRow[]>>; built_at: string }

// 경기와 배당 (core.core_macro_dividend_*). years 행 = [사업연도, ...year_cols 순서 값]
export interface Macro {
  year_cols: string[]; years: (number | null)[][]
  corr: [string, string, string, string, number | null, number | null, number | null, number | null][] // 시차, 보는 법, 배당 지표, 거시, Spearman, p, 연도 수, 회사×연도 행 수
  series: Record<string, Record<string, number | null>> // 항목 → 연도 → 값. 시차 거시 값은 '항목@prev'·'항목@decision'
  lags: [string, string][]; dividend_names: Record<string, string>; macro_names: Record<string, string>; built_at: string
  profit: ProfitDividend | null
}

// 회사 이익 변화와 주당배당금 변화 (source/scripts/analyze_profit_dividend.py → data/processed/analysis/profit_dividend.json)
export interface ProfitPair { profit: string; dividend: string; name: string; r: number; p: number; rows: number; companies: number }
export interface ProfitDividend {
  built: string; years: [number, number]; n_perm: number
  firm: ProfitPair[]; firm_ex_last: ProfitPair[]
  updown: [string, number, number, number][]; updown_ex_last: [string, number, number, number][] // 묶음, 회사·연도 수, 올린 비율, 줄인 비율
  by_year: [number, number, number, number, number][]
  year_agg: { name: string; r: number; p: number; n: number }
}

export interface HolderRow { 묶음: string; '회사 수': number; '지분 자료': number; 중앙값: number; '1사분위': number; '3사분위': number; '개인 최대주주(%)': number; 표시: boolean }

export interface EventSummary { kind: string; basis: string; ret: string; sample: string; window: number; n: number; median: number; p25: number; p75: number }
export interface Events {
  summary: EventSummary[]
  curves: Record<string, CurvePoint[]> // "공시 종류|기준일|수익률|표본|창"
  methods: {
    tests: Record<string, string | number | null>[]
    regression_60: { 모형: string; 변수: string; '계수(%p)': number; '군집 표준오차': number; p: number }[]
    n_regression_60: number
  } | null
}

// 해마다 [회사 번호, 배당성향(%), 증가율(%), 2026 판정]
export interface Movement {
  frames: Record<string, [number, number, number, Status | null][]>; basis: string
  grid: Record<string, number[][]> // 3장 칸 그림: [증가 10%↑ / 0~10% / 감소][배당성향 25% 미만 / 25~40% / 40%↑] 회사 수
  decrease_check?: { year: number; n: number; both: number; differ: number } // 칸 그림 '감소'(배당 총액) vs 법 제2호(배당소득)가 갈리는 회사
}

export interface Question { key: string; kind: Kind; ask: string; chips: string[] }
export type Kind = 'holdings' | 'amount' | 'other_dividend' | 'yesno' | 'base'

export interface DocsGuide { text: string; items: { title: string; how: string; links: { label: string; url: string }[] }[]; note: string }
export type EntryIntent = 'start' | 'decline' | 'help'

export interface Script {
  docs_chip: string; docs_guide: DocsGuide
  restart_words: string[]; stop_words: string[]; stop_reply: string; confirm_yes: string[]; confirm_no: string[]
  layout_fixed: string
  title: string; body: string; ai_note: string; step_labels: string[]; questions: Question[]
  step_help: Record<string, string>; dividend_types: Record<string, 'domestic' | 'foreign'>
  dividend_amount_ask: string; dividend_amount_chips: string[]; other_income_note: string
  receipt_chip: string; receipt_guide: string; no_wage: string; confirm_ask: string
  confirm_chips: string[]; confirm_note: string; edit_ask: string; parse_retry: string; stuck_hint: string
  max_chars: number; ai_read_mark: string; result_lead: string; next_check: string; result_actions: string[]
  result_footnote: string; send_result: string; send_result_note: string; law_notice: string; condition: string
  greeting: string; start_guide: string; entry_fallback: string; entry_unclear: string
  entry_words: Record<EntryIntent, string[]>; entry_replies: Record<'decline' | 'help', string>
   addon_chips: string[]; addon_replies: Record<string, string>
  scope_guide: string; company_list_chip: string; image_chip: string; image_note: string; image_guide: Record<'holdings' | 'base', { title: string; lines: string[] }>; image_guide_pick: string; image_reading: string; base_image_chip: string; base_image_note: string; base_image_reading: string; other_holding_added: string; other_holding_dup: string
  special_label: string; special_tax_label: string; special_tax_tag: string; special_tax_note: string; no_target: string
  term_chip: string; term_scope: string; term_examples: string[]
  special_legal: string; special_explain_title: string; special_explain: string[]
  stock_text: { shares: string; special: string; held: string; general: string; next_up: string; next_keep: string }
}

/** ① 보유 종목 캡처를 서버 안 AI가 읽은 결과. text는 입력창에 채워 고객이 확인한 뒤 보낸다 */
export interface ImageOut { ok: boolean; text?: string; amount?: number; gross?: number; bracket?: string; count?: number; missing?: string[]; reply?: string; error?: string }

export interface ParseOut {
  ok: boolean; value?: unknown; error?: string; by?: string
  guard?: string; reply?: string; consult?: boolean
  question?: boolean; faq?: Faq | null; help?: string
  skip?: '없음' | '모름'; code?: string; prompt?: string
  excluded?: string[]; note?: string // ①에서 조회 대상이 아니라 빼고 넘어간 종목과 그 안내
  add_holdings?: { company: string; shares: number }[]
  fixed_text?: string // 영문 자판으로 친 글을 한글로 바꿔 읽었을 때 그 글
  chat?: string // 인사·정체·사용법 같은 말에 정해 둔 답
  suggest_text?: string // 줄임말·옛 이름·오타 표로 바꾼 글: 입력창에 넣고 되묻는다
}

/** 금융 상식 고정 답변 (data/processed/faq/finance_faq.json). 문장은 미리 써 둔 그대로다 */
export interface DictTerm { term: string; aliases: string[]; definition: string; source_name: string; source_url: string; kind: 'fsc' | 'onepick' }

export interface Faq { id: string; title: string; answer: string; source_label: string; source_url: string; notice: string; by: string }

export interface CheckupIn {
  holdings: { company: string; shares: number }[]
  interest: number | null; other_domestic: number | null; other_foreign: number | null
  base: number | null; has_other_income: boolean
  holdings_answer?: '없음' | '모름' | null
  outside?: string[] // ①에서 고배당기업 목록에 없어 뺀 종목(보유 종목 수에만 셈)
}

export interface CheckupOut {
  headline: string
  tax: { status: string; rows: [string, number][]; difference: number | null; direction: string | null
    separate_tax: number; reasons: string[]; notice: string }
  stocks: (Stock & { shares: number; special: number; held: number })[]
  special_total: number; unknown_fields: string[]; notes: string[]
  no_target: string | null
}

export interface Passage { label: string; text: string; url: string; by?: string }

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { ...init, headers: { 'Content-Type': 'application/json', ...init?.headers } })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    // 개발 서버(vite)는 API 서버가 꺼져 있으면 JSON이 아닌 500을 돌려준다
    if (body === null) throw new Error('API 서버에 연결하지 못했어요. scripts.run_api가 켜져 있는지 확인해 주세요.')
    throw new Error(typeof body.detail === 'string' ? body.detail : `요청이 실패했어요 (${res.status})`)
  }
  return res.json() as Promise<T>
}

export interface IsaIrpBracket { key: 'low' | 'mid' | 'high' | 'biz_low' | 'biz_mid' | 'biz_high'; label: string; isa_type: string; isa_free: number; irp_permil: number; kind: 'wage' | 'business' }
export interface IrpCredit { irp: number; pension_saving: number; counted: number; over: number; rate_permil: number; credit: number; tax_due: number | null; refund: number; source: string }
export interface IsaIrp {
  brackets: IsaIrpBracket[]; chosen: IsaIrpBracket | null
  isa: { profit: number; normal: number; general: number; low_income: number; source: string }
  irp: IrpCredit[]
  compare: { name: string; who: string; benefit: string; limit: string }[]
  facts: { item: string; isa: string; irp: string }[]; facts_note: string; facts_source: string
  receipt: { no: string; item: string; use: string }[]; receipt_source: string
  isa_early: { problem: string; ways: { icon: string; title: string; text: string }[]; source: string }
  irp_withdraw: { reasons: { icon: string; title: string; text: string }[]; steps: { title: string; text: string }[]
    tax: { case: string; examples: string; tax: string }[]; note: string; source: string }
  why_not: { law: string; text: string }[]; notice: string; checked: string
  rate_table: RateTable
}
export interface RateTable {
  rows: { lower: number; upper: number | null; basic_permil: number; separate_permil: number }[]
  isa: { over_permil: number; free_general: number; free_low_income: number }
  irp: { pension_permil: number[]; separate_cap: number; over_permil: number; early_permil: number }
  normal_permil: number; threshold: number; source: string
}

export interface PersonaSummary { id: string; name: string; age: number; emoji: string; job: string; tag: string }
export interface Persona extends PersonaSummary {
  home: string; quote: string; goal: string
  income: [string, number][]; income_note: string
  accounts: [string, string][]
  financial: [string, string, number, 'interest' | 'stock' | 'fund'][]
  financial_total: number; financial_totals: { interest: number; stock: number; fund: number }; withheld_after: number
  answers: (string | null)[]
  checkup: CheckupOut
  isa_irp: {
    kind: 'wage' | 'business'; basis: string
    isa: { blocked_years: number[]; can_join: boolean; type: string; free: number; income_year: number; income: number
      normal_tax: number; isa_tax: number; profit: number; source: string }
    irp: IrpCredit & { income_year: number; income: number }
    what_if: { income: number; rate_permil: number; credit: number }[]
    notice: string; checked: string
  }
  isa_irp_note: string; pitfalls: string[]; next: string; source: string
}

export const api = {
  personas: () => call<PersonaSummary[]>('/api/personas'),
  persona: (id: string) => call<Persona>(`/api/personas/${encodeURIComponent(id)}`),
  baseImage: (image: string) => call<ImageOut>('/api/chat/base-image', { method: 'POST', body: JSON.stringify({ image }) }),
  holdingsImage: (image: string) => call<ImageOut>('/api/chat/holdings-image', { method: 'POST', body: JSON.stringify({ image }) }),
  companyList: () => call<{ name: string; code: string; pref_of: string }[]>('/api/companies/list'), // pref_of: 우선주면 보통주 회사 이름
  search: (q: string) => call<{ name: string; code: string }[]>(`/api/companies?q=${encodeURIComponent(q)}`),
  company: (code: string) => call<Stock>(`/api/companies/${encodeURIComponent(code)}`),
  funnel: () => call<Funnel>('/api/judgement/funnel'),
  analysis: () => call<Analysis>('/api/analysis'),
  events: () => call<Events>('/api/analysis/events'),
  movement: () => call<Movement>('/api/analysis/movement'),
  script: () => call<Script>('/api/chat/script'),
  parse: (kind: Kind, text: string, dividend_type?: string | null) =>
    call<ParseOut>('/api/chat/parse', { method: 'POST', body: JSON.stringify({ kind, text, dividend_type: dividend_type ?? null }) }),
  checkup: (body: CheckupIn) => call<CheckupOut>('/api/checkup', { method: 'POST', body: JSON.stringify(body) }),
  evidence: () => call<Passage[]>('/api/law/evidence'),
  race: (pick: number) => call<{ n_events: number; pick: number; year: number; market: string; path: [number, number, number][]; car_pct: number | null }>(`/api/column/race?pick=${pick}`),
  spread: () => call<{ values: number[]; basis: string }>('/api/column/spread'),
  lawPassages: () => call<(Passage & { effective: string })[]>('/api/law/passages'),
  separate: (amount: number) => call<{ amount: number; tax: number; effective_pct: number; source: string; notice: string
    steps: { from: number; to: number | null; rate_pct: number; part: number; tax: number }[] }>(`/api/tax/separate?amount=${amount}`),
  isaIrp: (q: { bracket: string | null; profit: number; irp: number; pension_saving: number }) =>
    call<IsaIrp>(`/api/isa-irp?${new URLSearchParams({ ...(q.bracket ? { bracket: q.bracket } : {}), profit: String(q.profit), irp: String(q.irp), pension_saving: String(q.pension_saving) })}`),
  terms: () => call<{ notice: Record<'fsc' | 'onepick', string>; terms: DictTerm[] }>('/api/terms'),
  lawSearch: (q: string) => call<{ notice: string; hits: Passage[] }>(`/api/law/search?q=${encodeURIComponent(q)}`),
}
