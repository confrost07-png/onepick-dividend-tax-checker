-- 원픽 분석 DB (PRD v0.2 6.2 테이블 설계)
-- raw  : 원천. 받은 파일 그대로 보관하고 고치지 않는다.
-- core : 분석용. raw를 가공한 회사·연도 단위 표와 판정·최소액 결과.
-- ref  : 기준표.
-- 금액은 원 단위(numeric). 백만 원 원천에서 바꾼 값은 *_unit 열에 원래 단위를 적는다.
-- 여러 번 실행해도 되도록 IF NOT EXISTS로 만든다.

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS ref;

-- ---------------------------------------------------------------- raw

CREATE TABLE IF NOT EXISTS raw.kind_list (
    corp_name        text PRIMARY KEY,
    corp_code        char(8),
    is_high_dividend text,          -- KIND 공시 원문 '고배당기업여부' (해당 / - / 추가 기재)
    final_rcept_no   text,
    final_disclosed_on text,
    decision_date    text,
    b2024_won        numeric,       -- 원문 2024 배당소득
    prev_year        text,
    prev_payout_pct  numeric,
    prev_d_won       numeric,       -- 원문 직전 이익배당금액
    prevprev_d_won   numeric,       -- 원문 전전 이익배당금액
    growth_pct       numeric,
    reduction_note   text,          -- 감액배당 문구
    link             text,
    source_file      text NOT NULL
);
COMMENT ON TABLE raw.kind_list IS 'KIND 고배당기업 목록 1곳 (09). KIND에는 코드가 없어 회사명으로 core_company와 연결';

CREATE TABLE IF NOT EXISTS raw.dart_dividend_item (
    corp_code   char(8) NOT NULL,
    corp_name   text,
    bsns_year   int NOT NULL,
    item        text,               -- 항목_DART원문
    stock_kind  text,               -- 주식종류_DART원문
    value       text,               -- 원문 값 그대로
    is_dash     text,
    col_02      text,               -- 02 파일의 대응 열 이름
    rcept_no    text,
    source_file text NOT NULL
);
COMMENT ON TABLE raw.dart_dividend_item IS 'OpenDART 배당에 관한 사항: 회사×사업연도×항목×주식종류 값 1개 (01). 원자료 그대로라 PK 없음';
CREATE INDEX IF NOT EXISTS dart_dividend_item_corp_year ON raw.dart_dividend_item (corp_code, bsns_year);

CREATE TABLE IF NOT EXISTS raw.dart_financial (
    corp_code     char(8) NOT NULL,
    corp_name     text,
    bsns_year     int NOT NULL,
    fs_div        text NOT NULL,    -- CFS(연결) / OFS(별도)
    sj_div        text NOT NULL,    -- BS(재무상태표) / CF(현금흐름표)
    account_nm    text,
    account_id    text,
    thstrm_amount numeric,          -- 당기금액(원)
    frmtrm_amount numeric,          -- 전기금액(원)
    term_name     text,
    ord           int NOT NULL,     -- DART 표시순서
    currency      text,
    rcept_no      text,
    source_file   text NOT NULL,
    PRIMARY KEY (corp_code, bsns_year, fs_div, sj_div, ord)
);
COMMENT ON TABLE raw.dart_financial IS '회사×사업연도×재무제표 종류×표시순서 1행 (04-2, 원 단위)';

CREATE TABLE IF NOT EXISTS raw.dividend_decision (
    rcept_no       text PRIMARY KEY,
    corp_code      char(8) NOT NULL,
    corp_name      text,
    fiscal_month   text,
    disclosed_on   text,
    report_nm      text,
    is_correction  boolean,
    div_kind       text,            -- 결산배당 / 중간배당 / 분기배당
    div_type       text,            -- 현금배당 등
    attributed_year int,            -- 귀속사업연도(추정)
    dps_common_won numeric,
    dps_pref_won   numeric,
    differential   text,
    yield_common_pct numeric,
    yield_pref_pct numeric,
    total_won      numeric,         -- 배당금총액(원)
    total_mil      numeric,         -- 배당금총액(백만원)
    record_date    text,
    pay_date       text,
    agm            text,
    agm_date       text,
    board_date     text,
    origin         text,
    parse_status   text,
    link           text,
    source_file    text NOT NULL
);
COMMENT ON TABLE raw.dividend_decision IS '배당 결의 1건 (05). 정정공시도 그대로 두고 core에서 최신 것만 씀';
CREATE INDEX IF NOT EXISTS dividend_decision_corp_year ON raw.dividend_decision (corp_code, attributed_year);

CREATE TABLE IF NOT EXISTS raw.cf_dividend_paid (
    corp_code      char(8) NOT NULL,
    corp_name      text,
    fiscal_month   text,
    bsns_year      int NOT NULL,
    fs_div         text,
    rcept_no       text,
    paid_mil       numeric,         -- 배당금지급액(백만원)
    prev_paid_mil  numeric,
    n_accounts     int,
    accounts       text,
    nci_paid_mil   numeric,         -- 참고: 비지배지분 배당
    check_accounts text,
    status         text,
    source_file    text NOT NULL,
    PRIMARY KEY (corp_code, bsns_year)
);
COMMENT ON TABLE raw.cf_dividend_paid IS '회사×사업연도 현금흐름표 배당금 지급액 1행 (04, 백만 원)';

CREATE TABLE IF NOT EXISTS raw.cf_dividend_account (
    corp_code     char(8) NOT NULL,
    corp_name     text,
    bsns_year     int NOT NULL,
    fs_div        text NOT NULL,
    judgement     text,             -- 포함 / 제외(...) / 확인필요
    account_nm    text,
    account_id    text,
    thstrm_amount numeric,
    frmtrm_amount numeric,
    term_name     text,
    ord           int NOT NULL,
    currency      text,
    rcept_no      text,
    source_file   text NOT NULL,
    PRIMARY KEY (corp_code, bsns_year, fs_div, ord)
);
COMMENT ON TABLE raw.cf_dividend_account IS '회사×사업연도×현금흐름표 배당 계정 1줄과 포함·제외 판정 (04-1, 원 단위)';

CREATE TABLE IF NOT EXISTS raw.krx_price_daily (
    corp_code   char(8) NOT NULL,
    trade_date  date NOT NULL,
    close_adj   numeric NOT NULL,   -- 수정 종가(원)
    source_file text NOT NULL,
    PRIMARY KEY (corp_code, trade_date)
);
COMMENT ON TABLE raw.krx_price_daily IS
    '회사×거래일 수정 종가 1행 (한국거래소 KRX 시세, pykrx로 받음). 상장 전·거래정지일은 행이 없음';

CREATE TABLE IF NOT EXISTS raw.krx_market_index (
    market      text NOT NULL,      -- KOSPI / KOSDAQ
    trade_date  date NOT NULL,
    close       numeric NOT NULL,
    source_file text NOT NULL,
    PRIMARY KEY (market, trade_date)
);
COMMENT ON TABLE raw.krx_market_index IS '시장×거래일 지수 종가 1행 (KRX market.csv). 이벤트 스터디의 시장 수익률';

CREATE TABLE IF NOT EXISTS raw.krx_day_status (
    corp_code   char(8) NOT NULL,
    stock_code  char(6) NOT NULL,
    trade_date  date NOT NULL,
    close_last  numeric,            -- 거래정지일에 KRX가 주는 직전 종가. 상장 전은 비어 있음
    status      text NOT NULL,      -- 상장 전 / 거래정지 / 마지막 거래 이후
    source_file text NOT NULL,
    PRIMARY KEY (corp_code, trade_date)
);
COMMENT ON TABLE raw.krx_day_status IS
    '주가가 빈 회사×거래일 1행과 빈 사유 (KRX 일별상태.csv). 종목코드는 대상목록.csv로 corp_code에 연결';

CREATE TABLE IF NOT EXISTS raw.ecos_macro (
    series       text NOT NULL,     -- 지표 이름 (source/core/macro.py SERIES, 예: usdkrw_d)
    time         text NOT NULL,     -- ECOS 시점 원문 (20180102 / 201801 / 2018Q1)
    period_start date NOT NULL,     -- 시점의 첫날. 일별은 그날, 월별은 1일, 분기는 분기 첫날
    cycle        char(1) NOT NULL,  -- D / M / Q
    value        numeric,
    value_raw    text,
    unit         text,
    label        text NOT NULL,
    stat_code    text NOT NULL,
    stat_name    text,
    item_code1   text NOT NULL,
    item_name1   text,
    item_code2   text,
    item_name2   text,
    source_file  text NOT NULL,
    PRIMARY KEY (series, time)
);
COMMENT ON TABLE raw.ecos_macro IS
    '지표×시점 1행 (한국은행 ECOS StatisticSearch, data/raw/macro/*.csv). 경상수지·금리·환율·GDP·CPI·고용, 값은 원문 그대로';

-- ---------------------------------------------------------------- core

CREATE TABLE IF NOT EXISTS core.core_company (
    corp_code       char(8) PRIMARY KEY,
    corp_name       text NOT NULL,
    stock_code      char(6) UNIQUE,
    market          text,
    fiscal_month    int,
    is_december_fye boolean,
    kind_type_2025  text,           -- KIND 공시 유형(우수형/노력형)
    kind_listed     boolean,        -- KIND 고배당 공시 원문 '해당'
    pref_stock_codes text,          -- 상장 우선주 코드 (07)
    pref_status     text,
    source_file     text NOT NULL
);
COMMENT ON TABLE core.core_company IS '회사 1곳 (02 + 07 + 09)';

CREATE TABLE IF NOT EXISTS core.core_dividend_year (
    corp_code       char(8) NOT NULL REFERENCES core.core_company (corp_code),
    bsns_year       int NOT NULL,
    d_dart_won      numeric,        -- DART 현금배당총액(결의 기준, 02)
    d_dart_unit     int,            -- 원천 단위(원): 1000000
    d_decision_won  numeric,        -- 배당 결정 공시 배당금총액 합계(원 단위 원값, 05, 정정은 최신 것만)
    decision_count  int,
    cf_paid_won     numeric,        -- 현금흐름표 배당금 지급액(지급 기준, 04)
    cf_paid_unit    int,
    cf_status       text,
    dps_common_won  numeric,
    b_won           numeric,        -- 배당소득 B. 감액배당·주식배당 확인 전이라 비워 둠
    b_status        text NOT NULL,  -- '미산출' 등
    source          text NOT NULL,  -- 행을 만든 원천 (02, 05 등)
    PRIMARY KEY (corp_code, bsns_year)
);
COMMENT ON TABLE core.core_dividend_year IS '회사×사업연도 배당 세 갈래(DART·결정 공시·현금흐름표)와 B. 서로 자동 대체하지 않음';

CREATE TABLE IF NOT EXISTS core.core_financial_year (
    corp_code        char(8) NOT NULL REFERENCES core.core_company (corp_code),
    bsns_year        int NOT NULL,
    fs_basis         text,          -- 연결 / 별도
    ni_owner_won     numeric,       -- 지배주주 순이익
    liabilities_won  numeric,
    equity_won       numeric,
    unit             int,           -- 원천 단위(원): 1000000
    source           text NOT NULL,
    PRIMARY KEY (corp_code, bsns_year)
);
COMMENT ON TABLE core.core_financial_year IS '회사×사업연도 지배주주 순이익·부채·자본 (02, 백만 원 → 원)';

CREATE TABLE IF NOT EXISTS core.core_judgement_2026 (
    corp_code      char(8) PRIMARY KEY REFERENCES core.core_company (corp_code),
    status         text NOT NULL,   -- 충족 / 미충족 / 판정 보류
    route          text,            -- 가목 / 나목
    deemed_payout_pct integer,      -- 적자로 간주한 배당성향(%) 25 / 0, 실제 배당성향이면 NULL (조특령 제104조의24⑤)
    tag            text NOT NULL,   -- 현재 해석 기준 / 판정 보류
    reasons        text,
    needs_recheck  boolean NOT NULL,
    b_prev_won     numeric,
    b_2024_won     numeric,
    d_prev_won     numeric,
    d_prevprev_won numeric,
    ni_prev_won    numeric,
    liabilities_won numeric,
    equity_won     numeric,
    engine         text NOT NULL,   -- 계산한 코드
    built_at       timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE core.core_judgement_2026 IS '회사 1곳의 2026 사업연도 배당 판정 (source/core/judgement.py)';
ALTER TABLE core.core_judgement_2026 ADD COLUMN IF NOT EXISTS deemed_payout_pct integer;

CREATE TABLE IF NOT EXISTS core.core_min_dividend_2027 (
    corp_code        char(8) NOT NULL REFERENCES core.core_company (corp_code),
    scenario         text NOT NULL, -- 최근 3년 최저 / 2025년 (기본) / 최근 3년 최고
    ni2026_won       numeric,
    status           text NOT NULL, -- 산출 / 충족 불가 / 판정 보류
    min_won          numeric,
    basis            text,
    reasons          text,
    ratio_to_2025_pct numeric,
    additional_won   numeric,
    pass_if_same_as_2025 boolean,
    engine           text NOT NULL,
    built_at         timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (corp_code, scenario)
);
COMMENT ON TABLE core.core_min_dividend_2027 IS '회사×순이익 시나리오 1행 최소 필요 배당액 (source/core/min_dividend.py)';

-- KRX 주가·지수 사용 등급. 원본(raw.krx_*)은 지우거나 고치지 않고 표시만 따로 둔다.
-- 주가에는 회사 표에 없는 회사(에코마케팅)도 있어 core_company FK를 걸지 않는다.
CREATE TABLE IF NOT EXISTS core.core_price_flag (
    corp_code   char(8) NOT NULL,
    trade_date  date NOT NULL,
    kind        text NOT NULL,      -- 상한 초과 등락 / 같은 가격 연속
    grade       text NOT NULL,      -- 주의 / 제외
    detail      text NOT NULL,
    rule        text NOT NULL,
    PRIMARY KEY (corp_code, trade_date, kind)
);
COMMENT ON TABLE core.core_price_flag IS '회사×거래일×문제 종류 1행 주가 표시 (source/core/price_quality.py). 표시 없는 날은 사용 가능';

CREATE TABLE IF NOT EXISTS core.core_index_flag (
    market      text NOT NULL,
    trade_date  date NOT NULL,
    kind        text NOT NULL,      -- 지수 급등락 미검증
    grade       text NOT NULL,
    detail      text NOT NULL,
    rule        text NOT NULL,
    PRIMARY KEY (market, trade_date, kind)
);
COMMENT ON TABLE core.core_index_flag IS '시장×거래일×문제 종류 1행 지수 표시 (source/core/price_quality.py)';

-- 회사×거래일 1행: 가격이 있는 날은 등급(사용 가능/주의/제외)과 사유, 빈 날은 '제외'와 빈 사유
CREATE OR REPLACE VIEW core.v_price_daily AS
SELECT p.corp_code, p.trade_date, p.close_adj,
       coalesce(f.grade, '사용 가능') AS grade,
       f.reasons
FROM raw.krx_price_daily p
LEFT JOIN LATERAL (
    SELECT CASE WHEN bool_or(x.grade = '제외') THEN '제외' ELSE '주의' END AS grade,
           string_agg(x.kind || ': ' || x.detail, ' / ' ORDER BY x.kind) AS reasons
    FROM core.core_price_flag x
    WHERE x.corp_code = p.corp_code AND x.trade_date = p.trade_date
    HAVING count(*) > 0
) f ON true
UNION ALL
SELECT s.corp_code, s.trade_date, NULL, '제외', '빈칸: ' || s.status
FROM raw.krx_day_status s;
COMMENT ON VIEW core.v_price_daily IS '주가 사용 등급. 분석은 grade = ''사용 가능''(또는 ''주의''까지)만 쓴다';

CREATE OR REPLACE VIEW core.v_index_daily AS
SELECT m.market, m.trade_date, m.close,
       CASE WHEN bool_or(f.grade = '제외') THEN '제외' WHEN count(f.kind) > 0 THEN '주의' ELSE '사용 가능' END AS grade,
       string_agg(f.kind || ': ' || f.detail, ' / ' ORDER BY f.kind) AS reasons
FROM raw.krx_market_index m
LEFT JOIN core.core_index_flag f USING (market, trade_date)
GROUP BY m.market, m.trade_date, m.close;
COMMENT ON VIEW core.v_index_daily IS '지수 사용 등급';

-- 회사 1곳의 주가 수집 범위. 회사 표에 있는데 주가가 하나도 없으면 '미수집'
CREATE OR REPLACE VIEW core.v_price_coverage AS
SELECT c.corp_code, c.corp_name, c.stock_code, c.market,
       CASE WHEN g.days IS NULL THEN '미수집' ELSE '수집' END AS coverage,
       g.days, g.first_date, g.last_date, g.ok_days, g.caution_days, g.excluded_days
FROM core.core_company c
LEFT JOIN (
    SELECT corp_code, count(*) AS days, min(trade_date) AS first_date, max(trade_date) AS last_date,
           count(*) FILTER (WHERE grade = '사용 가능') AS ok_days,
           count(*) FILTER (WHERE grade = '주의') AS caution_days,
           count(*) FILTER (WHERE grade = '제외') AS excluded_days
    FROM core.v_price_daily WHERE close_adj IS NOT NULL GROUP BY corp_code
) g USING (corp_code);
COMMENT ON VIEW core.v_price_coverage IS '회사별 주가 수집 여부와 등급별 일수';

CREATE TABLE IF NOT EXISTS core.core_event_car (
    kind          text NOT NULL,    -- 주당배당금 증가 / 주당배당금 유지·감소 / 고배당기업 공시(KIND)
    rcept_no      text NOT NULL,
    window_days   int NOT NULL,     -- 이벤트일 0 ~ N거래일
    corp_code     char(8) NOT NULL,
    disclosed_on  date NOT NULL,
    event_date    date,
    market        text,             -- 비교 지수 KOSPI / KOSDAQ
    car           double precision, -- 누적 초과수익률(소수, 0.01 = 1%p)
    status        text NOT NULL,    -- 산출 / 제외
    reason        text,             -- 제외 사유
    caution       boolean NOT NULL, -- 창 안에 '주의'일(멈춘 가격 5~19일, 미검증 지수)이 있음
    engine        text NOT NULL,
    built_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (kind, rcept_no, window_days)
);
COMMENT ON TABLE core.core_event_car IS '공시 1건×관측 기간 1행 누적 초과수익률 (source/core/event_study.py). 회사별 값은 화면에 보이지 않음';

CREATE TABLE IF NOT EXISTS core.core_event_summary (
    kind          text NOT NULL,
    period        text NOT NULL,    -- 2025년까지 / 2026년 (지수 미검증)
    window_days   int NOT NULL,
    n_cases       int NOT NULL,
    median_pct    numeric,          -- %p, 사례 10건 미만이면 비움
    p25_pct       numeric,
    p75_pct       numeric,
    shown         boolean NOT NULL,
    n_caution     int NOT NULL,
    n_excluded    int NOT NULL,
    engine        text NOT NULL,
    built_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (kind, period, window_days)
);
COMMENT ON TABLE core.core_event_summary IS '공시 종류×기간×관측 기간 1행 CAR 집계 (과거 사례 리포트 화면용)';

CREATE TABLE IF NOT EXISTS core.core_event_curve (
    kind          text NOT NULL,
    period        text NOT NULL,
    window_days   int NOT NULL,
    day           int NOT NULL,     -- 이벤트일 0 ~ window_days
    n_cases       int NOT NULL,
    median_pct    numeric,          -- 그날까지 누적 초과수익률(%p), 사례 10건 미만이면 비움
    p25_pct       numeric,
    p75_pct       numeric,
    engine        text NOT NULL,
    built_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (kind, period, window_days, day)
);
COMMENT ON TABLE core.core_event_curve IS '공시 종류×기간×관측 기간×날짜 1행 누적 초과수익률 곡선 (S-01 화면 곡선)';

-- 이벤트 기준일(공시일·주주총회 결의일·배당락일), 수익률(주가만·배당 포함), 표본(전체·자본 변동 겹침 제외) 차원 (2026-10-25)
ALTER TABLE core.core_event_car ADD COLUMN IF NOT EXISTS basis text NOT NULL DEFAULT '공시일';
ALTER TABLE core.core_event_car ADD COLUMN IF NOT EXISTS car_total double precision;      -- 배당 포함 CAR
ALTER TABLE core.core_event_car ADD COLUMN IF NOT EXISTS dps numeric;                      -- 더한 주당배당금
ALTER TABLE core.core_event_car ADD COLUMN IF NOT EXISTS record_date date;                 -- 그 배당의 기준일
ALTER TABLE core.core_event_car ADD COLUMN IF NOT EXISTS overlap_capital boolean NOT NULL DEFAULT false;  -- 창 안 증자·감자 공시
ALTER TABLE core.core_event_car DROP CONSTRAINT IF EXISTS core_event_car_pkey;
ALTER TABLE core.core_event_car ADD PRIMARY KEY (kind, rcept_no, window_days, basis);
ALTER TABLE core.core_event_summary ADD COLUMN IF NOT EXISTS basis text NOT NULL DEFAULT '공시일';
ALTER TABLE core.core_event_summary ADD COLUMN IF NOT EXISTS return_type text NOT NULL DEFAULT '주가만';
ALTER TABLE core.core_event_summary ADD COLUMN IF NOT EXISTS sample text NOT NULL DEFAULT '전체';
ALTER TABLE core.core_event_summary DROP CONSTRAINT IF EXISTS core_event_summary_pkey;
ALTER TABLE core.core_event_summary ADD PRIMARY KEY (kind, period, window_days, basis, return_type, sample);
ALTER TABLE core.core_event_curve ADD COLUMN IF NOT EXISTS basis text NOT NULL DEFAULT '공시일';
ALTER TABLE core.core_event_curve ADD COLUMN IF NOT EXISTS return_type text NOT NULL DEFAULT '주가만';
ALTER TABLE core.core_event_curve ADD COLUMN IF NOT EXISTS sample text NOT NULL DEFAULT '전체';
ALTER TABLE core.core_event_curve DROP CONSTRAINT IF EXISTS core_event_curve_pkey;
ALTER TABLE core.core_event_curve ADD PRIMARY KEY (kind, period, window_days, day, basis, return_type, sample);

-- DB 빈칸을 DART 원문에서 다시 읽은 값 (source/core/dart_fill.py, source/scripts/fill_from_dart.py).
-- 원본 표는 고치지 않는다. 아래 뷰가 원본 값이 비었을 때만 status='채움'인 값을 끼워 넣고 filled_items로 표시한다.
CREATE TABLE IF NOT EXISTS core.core_dart_fill (
    corp_code       char(8) NOT NULL,
    bsns_year       int NOT NULL,
    item            text NOT NULL,      -- ni_owner_won / liabilities_won / equity_won / dps_common_won / cf_paid_won
                                        -- decision.* (원래 배당 결정 공시) / ofs.* (별도재무제표 보완 자료 항목)
    ref             text NOT NULL DEFAULT '',  -- decision.*: 원공시 접수번호
    value_won       numeric,
    value_text      text,
    status          text NOT NULL,      -- 채움 / 확인 필요 / 무배당 확인 / 원문도 비어 있음 / 계산 대상 아님 / 정책 대기
    source_rcept_no text,
    source_title    text,
    source_url      text,
    column_kind     text,               -- 당기 / 비교기간(재작성 가능)
    fs_kind         text,               -- 연결 / 별도
    check_result    text,               -- 같은 표 안 합계 검산 결과
    note            text,
    engine          text NOT NULL,
    built_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (corp_code, bsns_year, item, ref)
);
COMMENT ON TABLE core.core_dart_fill IS '빈칸 1칸당 DART 원문 재확인 결과 1행. 원본 표는 고치지 않음';

CREATE OR REPLACE VIEW core.v_financial_year_filled AS
SELECT f.corp_code, f.bsns_year, f.fs_basis,
       coalesce(f.ni_owner_won, ni.value_won) AS ni_owner_won,
       coalesce(f.liabilities_won, li.value_won) AS liabilities_won,
       coalesce(f.equity_won, eq.value_won) AS equity_won,
       nullif(concat_ws(', ',
           CASE WHEN f.ni_owner_won IS NULL AND ni.value_won IS NOT NULL THEN 'ni_owner_won' END,
           CASE WHEN f.liabilities_won IS NULL AND li.value_won IS NOT NULL THEN 'liabilities_won' END,
           CASE WHEN f.equity_won IS NULL AND eq.value_won IS NOT NULL THEN 'equity_won' END), '') AS filled_items
FROM core.core_financial_year f
LEFT JOIN core.core_dart_fill ni ON ni.corp_code = f.corp_code AND ni.bsns_year = f.bsns_year AND ni.item = 'ni_owner_won' AND ni.status = '채움'
LEFT JOIN core.core_dart_fill li ON li.corp_code = f.corp_code AND li.bsns_year = f.bsns_year AND li.item = 'liabilities_won' AND li.status = '채움'
LEFT JOIN core.core_dart_fill eq ON eq.corp_code = f.corp_code AND eq.bsns_year = f.bsns_year AND eq.item = 'equity_won' AND eq.status = '채움';
COMMENT ON VIEW core.v_financial_year_filled IS '재무 + DART 원문으로 채운 값. filled_items에 채운 열 이름';

CREATE OR REPLACE VIEW core.v_dividend_year_filled AS
SELECT d.corp_code, d.bsns_year, coalesce(d.d_dart_won, dd.value_won) AS d_dart_won,
       coalesce(d.d_decision_won, dec.value_won) AS d_decision_won,
       coalesce(d.cf_paid_won, cf.value_won) AS cf_paid_won,
       coalesce(d.dps_common_won, dps.value_won) AS dps_common_won,
       d.b_won, d.b_status,
       nullif(concat_ws(', ',
           CASE WHEN d.d_dart_won IS NULL AND dd.value_won IS NOT NULL THEN 'd_dart_won' END,
           CASE WHEN d.d_decision_won IS NULL AND dec.value_won IS NOT NULL THEN 'd_decision_won' END,
           CASE WHEN d.cf_paid_won IS NULL AND cf.value_won IS NOT NULL THEN 'cf_paid_won' END,
           CASE WHEN d.dps_common_won IS NULL AND dps.value_won IS NOT NULL THEN 'dps_common_won' END), '') AS filled_items
FROM core.core_dividend_year d
LEFT JOIN core.core_dart_fill dd ON dd.corp_code = d.corp_code AND dd.bsns_year = d.bsns_year AND dd.item = 'd_dart_won' AND dd.status = '채움'
LEFT JOIN core.core_dart_fill cf ON cf.corp_code = d.corp_code AND cf.bsns_year = d.bsns_year AND cf.item = 'cf_paid_won' AND cf.status = '채움'
LEFT JOIN core.core_dart_fill dps ON dps.corp_code = d.corp_code AND dps.bsns_year = d.bsns_year AND dps.item = 'dps_common_won' AND dps.status = '채움'
LEFT JOIN (SELECT corp_code, bsns_year, sum(value_won) AS value_won FROM core.core_dart_fill
           WHERE item = 'decision.total_won' AND status = '채움' GROUP BY 1, 2) dec
       ON dec.corp_code = d.corp_code AND dec.bsns_year = d.bsns_year;
COMMENT ON VIEW core.v_dividend_year_filled IS '배당 + DART 원문으로 채운 값(현금배당총액 D·원래 결정 공시·주당배당금·현금흐름표 지급액). filled_items에 채운 열 이름';

-- DB 재무제표 값 ↔ 그 연도 자기 사업보고서(DART 원문) 한 칸씩 대조 (source/core/dart_verify.py, source/scripts/verify_db.py)
CREATE TABLE IF NOT EXISTS core.core_dart_verify (
    target        text NOT NULL,      -- core_financial_year / cf_dividend_paid / dart_financial
    corp_code     char(8) NOT NULL,
    bsns_year     int NOT NULL,
    item          text NOT NULL,      -- ni_owner_won / liabilities_won / equity_won / dividends_paid_won
    basis         text NOT NULL,      -- 연결 / 별도
    db_value      numeric,
    src_value     numeric,
    result        text NOT NULL,      -- 일치 / 일치(단위 반올림) / 불일치 / 원문 못 읽음 / 원문 없음
    src_rcept_no  text,
    src_title     text,
    src_period    text,               -- 사업보고서 기간 YYYY.MM
    check_result  text,               -- 원문 표 안 검산 결과
    note          text,               -- 불일치일 때 DB 값이 어느 원문 값과 같은지
    engine        text NOT NULL,
    built_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (target, corp_code, bsns_year, item, basis)
);
COMMENT ON TABLE core.core_dart_verify IS 'DB 재무제표 값 1칸 ↔ DART 사업보고서 원문 대조 결과 1행. 원본 표는 고치지 않음';

-- 원문 대조에서 불일치한 칸을 원문 값으로 바꿔 보는 뷰. 원본 표는 그대로 둔다.
-- 칸마다 구분: 확실(원인 확인) / 재작성 선택(DB가 1~2년 뒤 재작성 값) / 사람 확인(원인 모름)
CREATE TABLE IF NOT EXISTS core.core_setting (
    key   text PRIMARY KEY,
    value text NOT NULL,
    note  text
);
INSERT INTO core.core_setting VALUES
    ('restated_policy', 'original', 'original: 그 연도 원래 공시 값 사용 / restated: DB의 재작성 값 유지 (팀 결정 전 임시)')
ON CONFLICT (key) DO NOTHING;

CREATE OR REPLACE VIEW core.v_dart_mismatch AS
SELECT v.*,
       CASE WHEN v.note LIKE '%뒤 보고서%' THEN '재작성 선택'
            WHEN v.note ~ '다른 기준|당기순이익 전체|통화 다름|정정 전|단위' THEN '확실'
            ELSE '사람 확인' END AS correction_kind,
       CASE WHEN v.check_result LIKE '%줄 없음%' THEN false  -- 원문에서 줄을 못 찾아 0이 된 칸은 원문 값이 아님
            WHEN v.note LIKE '%뒤 보고서%'
                 AND (SELECT value FROM core.core_setting WHERE key = 'restated_policy') = 'restated' THEN false
            ELSE true END AS use_source
FROM core.core_dart_verify v
WHERE v.result = '불일치' AND v.src_value IS NOT NULL;
COMMENT ON VIEW core.v_dart_mismatch IS '원문 대조 불일치 칸과 고칠지(use_source)·구분(correction_kind). 사람 검토 대상';

-- 사람이 원문을 보고 확정한 값 (전수 검산표 검토본, source/scripts/load_review_workbook.py). 있으면 아래 verified 뷰가 가장 먼저 쓴다.
-- value_won이 NULL인 행은 '원문에도 값 없음(빈칸)'으로 확정한 칸
CREATE TABLE IF NOT EXISTS core.core_review_value (
    target     text NOT NULL,       -- financial(02_재무) / dividend(02_배당표·04_배당금지급) / dividend_item(02_배당표_전체항목)
    corp_code  char(8) NOT NULL,
    bsns_year  int NOT NULL,
    item       text NOT NULL,       -- ni_owner_won · liabilities_won · equity_won · d_dart_won · dps_common_won · cf_paid_won · 전체항목 열 이름
    value_won  numeric,
    status     text,                -- 검토 상태 (확인완료 / 정정됨(배제) / 원문 대조)
    reviewer   text,
    memo       text,
    source     text NOT NULL,       -- 검토 파일 이름 또는 원문 대조 파일
    PRIMARY KEY (target, corp_code, bsns_year, item)
);
COMMENT ON TABLE core.core_review_value IS '전수 검산표 검토본에서 확정한 칸 1행 (원문 대조로 고친 칸 포함). 원천 표는 그대로 두고 verified 뷰가 덮어씀';

CREATE OR REPLACE VIEW core.v_financial_year_verified AS
SELECT f.corp_code, f.bsns_year, f.fs_basis,
       CASE WHEN rni.item IS NOT NULL THEN rni.value_won WHEN ni.use_source THEN ni.src_value ELSE f.ni_owner_won END AS ni_owner_won,
       CASE WHEN rli.item IS NOT NULL THEN rli.value_won WHEN li.use_source THEN li.src_value ELSE f.liabilities_won END AS liabilities_won,
       CASE WHEN req.item IS NOT NULL THEN req.value_won WHEN eq.use_source THEN eq.src_value ELSE f.equity_won END AS equity_won,
       f.filled_items,
       nullif(concat_ws(', ',
           CASE WHEN ni.use_source THEN 'ni_owner_won(' || ni.correction_kind || ')' END,
           CASE WHEN li.use_source THEN 'liabilities_won(' || li.correction_kind || ')' END,
           CASE WHEN eq.use_source THEN 'equity_won(' || eq.correction_kind || ')' END), '') AS corrected_items,
       nullif(concat_ws(', ',
           CASE WHEN rni.value_won IS DISTINCT FROM (CASE WHEN ni.use_source THEN ni.src_value ELSE f.ni_owner_won END)
                     AND rni.item IS NOT NULL THEN 'ni_owner_won' END,
           CASE WHEN rli.value_won IS DISTINCT FROM (CASE WHEN li.use_source THEN li.src_value ELSE f.liabilities_won END)
                     AND rli.item IS NOT NULL THEN 'liabilities_won' END,
           CASE WHEN req.value_won IS DISTINCT FROM (CASE WHEN eq.use_source THEN eq.src_value ELSE f.equity_won END)
                     AND req.item IS NOT NULL THEN 'equity_won' END), '') AS reviewed_items
FROM core.v_financial_year_filled f
LEFT JOIN core.v_dart_mismatch ni ON ni.target = 'core_financial_year' AND ni.corp_code = f.corp_code
     AND ni.bsns_year = f.bsns_year AND ni.item = 'ni_owner_won'
LEFT JOIN core.v_dart_mismatch li ON li.target = 'core_financial_year' AND li.corp_code = f.corp_code
     AND li.bsns_year = f.bsns_year AND li.item = 'liabilities_won'
LEFT JOIN core.v_dart_mismatch eq ON eq.target = 'core_financial_year' AND eq.corp_code = f.corp_code
     AND eq.bsns_year = f.bsns_year AND eq.item = 'equity_won'
LEFT JOIN core.core_review_value rni ON rni.target = 'financial' AND rni.corp_code = f.corp_code
     AND rni.bsns_year = f.bsns_year AND rni.item = 'ni_owner_won'
LEFT JOIN core.core_review_value rli ON rli.target = 'financial' AND rli.corp_code = f.corp_code
     AND rli.bsns_year = f.bsns_year AND rli.item = 'liabilities_won'
LEFT JOIN core.core_review_value req ON req.target = 'financial' AND req.corp_code = f.corp_code
     AND req.bsns_year = f.bsns_year AND req.item = 'equity_won';
COMMENT ON VIEW core.v_financial_year_verified IS '재무: 사람 검토 확정 값 > 불일치 칸 원문 값 > 빈칸 채움 > DB. reviewed_items에 검토로 값이 바뀐 열';

CREATE OR REPLACE VIEW core.v_dividend_year_verified AS
SELECT d.corp_code, d.bsns_year,
       CASE WHEN rd.item IS NOT NULL THEN rd.value_won ELSE d.d_dart_won END AS d_dart_won,
       d.d_decision_won, d.cf_paid_won,
       CASE WHEN rp.item IS NOT NULL THEN rp.value_won ELSE d.dps_common_won END AS dps_common_won,
       d.b_won, d.b_status, d.filled_items,
       CASE WHEN rc.item IS NOT NULL THEN rc.value_won WHEN cf.use_source THEN cf.src_value ELSE d.cf_paid_won END AS cf_paid_won_verified,
       CASE WHEN cf.use_source THEN 'cf_paid_won(' || cf.correction_kind || ')' END AS corrected_items,
       nullif(concat_ws(', ',
           CASE WHEN rd.item IS NOT NULL AND rd.value_won IS DISTINCT FROM d.d_dart_won THEN 'd_dart_won' END,
           CASE WHEN rp.item IS NOT NULL AND rp.value_won IS DISTINCT FROM d.dps_common_won THEN 'dps_common_won' END,
           CASE WHEN rc.item IS NOT NULL AND rc.value_won IS DISTINCT FROM
                     (CASE WHEN cf.use_source THEN cf.src_value ELSE d.cf_paid_won END) THEN 'cf_paid_won' END), '') AS reviewed_items
FROM core.v_dividend_year_filled d
LEFT JOIN core.v_dart_mismatch cf ON cf.target = 'cf_dividend_paid' AND cf.corp_code = d.corp_code
     AND cf.bsns_year = d.bsns_year
LEFT JOIN core.core_review_value rd ON rd.target = 'dividend' AND rd.corp_code = d.corp_code
     AND rd.bsns_year = d.bsns_year AND rd.item = 'd_dart_won'
LEFT JOIN core.core_review_value rp ON rp.target = 'dividend' AND rp.corp_code = d.corp_code
     AND rp.bsns_year = d.bsns_year AND rp.item = 'dps_common_won'
LEFT JOIN core.core_review_value rc ON rc.target = 'dividend' AND rc.corp_code = d.corp_code
     AND rc.bsns_year = d.bsns_year AND rc.item = 'cf_paid_won';
COMMENT ON VIEW core.v_dividend_year_verified IS '배당: 사람 검토 확정 값(D·주당배당금·배당금 지급) > 현금흐름표 불일치 칸 원문 값 > 빈칸 채움 > DB';

-- ---------------------------------------------------------------- ref

CREATE TABLE IF NOT EXISTS ref.tax_rate (
    rule        text NOT NULL,      -- 분리과세 / 기본세율
    lower_bound bigint NOT NULL,
    base_tax    bigint NOT NULL,
    rate_pct    int NOT NULL,
    valid_from  date NOT NULL,
    source      text NOT NULL,
    status      text NOT NULL,      -- 공식 자료 확인 / 확인 필요
    PRIMARY KEY (rule, lower_bound, valid_from)
);
COMMENT ON TABLE ref.tax_rate IS '세율 구간 1개(시행일·출처·확인 상태) (source/core/tax_rates.py)';

-- 재무 숫자 밖의 원천 표(회사 목록·배당 표 전체 항목·배당 결정 공시·KIND 고배당 공시) ↔ DART 원문 대조 (source/scripts/verify_sources.py)
CREATE TABLE IF NOT EXISTS core.core_source_verify (
    target        text NOT NULL,      -- core_company / dart_dividend_item / dividend_decision / kind_list
    corp_code     char(8) NOT NULL,
    bsns_year     int,                -- 배당 표만 (그 칸의 사업연도)
    ref           text NOT NULL,      -- 대조한 행을 찾는 열쇠: 접수번호, 배당 표면 '접수번호|항목|종류|n번째'
    item          text NOT NULL,      -- 대조한 칸 (원천 표의 열 이름)
    db_value      text,
    src_value     text,               -- 원문에서 읽은 글자 (못 찾으면 NULL)
    result        text NOT NULL,      -- 일치 / 불일치 / 원문에서 못 찾음
    src_rcept_no  text,
    note          text,
    engine        text NOT NULL,
    built_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (target, ref, item)
);
COMMENT ON TABLE core.core_source_verify IS '원천 표 1칸 ↔ DART 원문 대조 1행 (회사 목록·배당 표·배당 결정·KIND). 원본 표는 고치지 않음';

-- F-06 재무 여력 (source/scripts/build_capacity.py, source/core/capacity.py). 합격점 없음
CREATE TABLE IF NOT EXISTS core.core_capacity_2025 (
    corp_code       char(8) PRIMARY KEY,
    industry        text,               -- DART 기업개황 업종명
    status          text NOT NULL,      -- 표시 / 미적용(금융업) / 미표시(최소액 보류·충족 불가)
    fs_div          text,
    ocf_won         numeric,            -- 영업활동 현금흐름 (2025)
    capex_won       numeric,            -- 유형자산 취득 (2025, 절댓값)
    fcf_won         numeric,            -- 영업활동 현금흐름 − 유형자산 취득
    min_won         numeric,            -- 2027 최소 필요 배당액 (2025년 기본 시나리오)
    cover_x         numeric,            -- fcf ÷ min (배)
    roe_pct         numeric,
    debt_pct        numeric,
    industry_median_cover numeric,
    median_basis    text,
    rcept_no        text,
    note            text,
    built_at        timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE core.core_capacity_2025 IS 'F-06 재무 여력: (영업CF − 유형자산 취득) ÷ 최소 필요 배당액, ROE·부채비율, 업종 중앙값. 금융업 미적용';

-- 시연 10개사 (source/scripts/select_demo10.py): 2026 판정 충족 + 기업가치 제고 계획 공시 + 금융업 제외 + 시가총액(추정) 상위
CREATE TABLE IF NOT EXISTS core.core_demo_company (
    rank          int PRIMARY KEY,
    corp_code     char(8) NOT NULL UNIQUE,
    corp_name     text NOT NULL,
    industry      text,
    mcap_est_won  numeric,       -- 추정 시가총액 = (자본금 ÷ 액면가) × 마지막 수정주가. 우선주가 섞여 실제와 다를 수 있음
    price_date    date,
    valueup_count int,           -- 기업가치 제고 계획 공시 수
    last_valueup_rcept text,
    rule          text NOT NULL,
    built_at      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE core.core_demo_company IS '시연 10개사 (F-03 밸류업 비교·F-06·F-07 대상). 선정 규칙은 rule 열';

-- F-03·F-07: 사람이 원문 확인을 마친 밸류업 배당 목표·배당 정책 항목 (source/scripts/load_policy_review.py)
CREATE TABLE IF NOT EXISTS core.core_policy_item (
    corp_code     char(8) NOT NULL,
    rcept_no      text NOT NULL,      -- 기업가치 제고 계획 공시 접수번호
    seq           int NOT NULL,       -- 그 공시 안 순번
    section       text NOT NULL,      -- 원문 위치 (2. 주요 내용 등)
    category      text NOT NULL,      -- 배당 목표 / 자사주 / 주주환원율 / 투자 계획
    text          text NOT NULL,      -- 원문 글자 그대로
    target_kind   text,               -- 배당성향 / 주당배당금 / 총액
    target_value  text,
    basis_note    text,
    use_as_target boolean NOT NULL DEFAULT false,  -- F-03 밸류업 비교에 쓸 목표
    reviewer      text NOT NULL,
    memo          text,
    loaded_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (corp_code, rcept_no, seq)
);
ALTER TABLE core.core_policy_item ADD COLUMN IF NOT EXISTS target_year int;  -- 목표 대상 사업연도 (이행 대조용)
COMMENT ON TABLE core.core_policy_item IS '검토자가 확인완료로 표시한 밸류업 배당 목표·정책 문장. 화면은 이 표에 있는 항목만 보여 줌';

-- 배당·주주환원 정책 문서 DB (source/core/policy_docs.py, source/scripts/collect_policy_docs.py)
-- 공시 1건 → 문서(본문·첨부 HTML·첨부 PDF) n개 → 문단 n개. 원본 파일은 data/raw/policy_docs/에 두고 경로·해시만 기록
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE TABLE IF NOT EXISTS raw.policy_filing (
    rcept_no     text PRIMARY KEY,
    corp_code    char(8) NOT NULL,
    corp_name    text,
    rcept_dt     date NOT NULL,
    report_nm    text NOT NULL,
    doc_kind     text NOT NULL,     -- 기업가치 제고 계획 / 기업지배구조보고서 / 주주환원·배당정책 공정공시
    is_correction boolean NOT NULL, -- [기재정정]·[첨부정정] 등
    n_docs       int NOT NULL,
    status       text NOT NULL,     -- 수집 / 원문 받기 실패
    note         text,
    fetched_at   timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS raw.policy_document (
    rcept_no     text NOT NULL REFERENCES raw.policy_filing (rcept_no) ON DELETE CASCADE,
    dcm_no       text NOT NULL,     -- body = 본문, 숫자 = 첨부서류(HTML), 숫자-n = 첨부 PDF n번째
    doc_name     text,
    file_type    text NOT NULL,     -- html / pdf
    n_pages      int,               -- PDF 쪽 수
    url          text NOT NULL,
    file_path    text NOT NULL,     -- 원본 파일 (data/ 기준 상대 경로, git 제외)
    sha256       char(64) NOT NULL,
    n_chars      int NOT NULL,
    text         text NOT NULL,     -- 원문 글자 (표 칸은 ' | ')
    PRIMARY KEY (rcept_no, dcm_no)
);
CREATE TABLE IF NOT EXISTS raw.policy_chunk (
    rcept_no     text NOT NULL,
    dcm_no       text NOT NULL,
    seq          int NOT NULL,      -- 문서 안 순서
    page         int,               -- PDF 쪽 번호 (HTML이면 비움)
    text         text NOT NULL,     -- 원문 글자 그대로 (최대 약 600자)
    PRIMARY KEY (rcept_no, dcm_no, seq),
    FOREIGN KEY (rcept_no, dcm_no) REFERENCES raw.policy_document (rcept_no, dcm_no) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS policy_chunk_trgm ON raw.policy_chunk USING gin (text gin_trgm_ops);
COMMENT ON TABLE raw.policy_filing IS '배당·주주환원 정책 공시 1건 (2024년부터, 638사)';
COMMENT ON TABLE raw.policy_document IS '공시의 본문·첨부서류 1개의 원문 글자와 원본 파일 경로·해시';
COMMENT ON TABLE raw.policy_chunk IS '검색용 문단 (원문 그대로, pg_trgm 색인). PDF는 쪽마다 한 벌: 글자층 + 글자층에 없는 OCR 줄(보충), 그림 쪽은 OCR (source/scripts/ocr_policy_docs.py rebuild_chunks)';
-- OCR: 글자층 없는 그림 PDF 쪽은 macOS Vision으로 글자 인식 (source/scripts/ocr_policy_docs.py)
ALTER TABLE raw.policy_chunk ADD COLUMN IF NOT EXISTS method text NOT NULL DEFAULT '글자층';  -- 글자층 / OCR / OCR 정정 / OCR 보충 / OCR 정정 보충
ALTER TABLE raw.policy_document ADD COLUMN IF NOT EXISTS n_ocr_pages int;                   -- OCR로 글자를 읽은 쪽 수
-- PDF 쪽마다 OCR 결과 1행 (전 쪽 OCR). 빈 쪽·실패도 행을 남겨 '빠짐없이 처리'를 셀 수 있게 하고,
-- OCR만 출처인 쪽과 신뢰도 낮은 줄이 남은 쪽은 사람 검토 (source/scripts/export_ocr_review.py → load_ocr_review.py)
CREATE TABLE IF NOT EXISTS raw.policy_page_ocr (
    rcept_no      text NOT NULL,
    dcm_no        text NOT NULL,
    page          int NOT NULL,
    run           text NOT NULL,      -- OCR 방식 판 (source/scripts/ocr_policy_docs.py RUN)
    status        text NOT NULL,      -- 글자 있음 / 빈 쪽 / 실패
    layer_chars   int NOT NULL,       -- 글자층 글자 수 (공백 제외)
    ocr_chars     int NOT NULL,       -- OCR 글자 수 (공백 제외)
    n_lines       int NOT NULL,
    n_low_lines   int NOT NULL,       -- 신뢰도 0.5 미만 줄 수
    conf_min      numeric(4,3),
    conf_avg      numeric(4,3),
    scale         numeric(3,1) NOT NULL,  -- 고른 결과의 확대 배율 (2.5, 낮은 줄이 있으면 4.0으로 다시 읽음)
    low_lines     text,               -- 신뢰도 낮은 줄 (검토자가 먼저 볼 곳)
    text          text NOT NULL,      -- OCR 글자 (줄 사이 \n)
    note          text,
    needs_review  boolean NOT NULL,   -- OCR만 출처(글자층 40자 미만)이거나 낮은 줄이 남음
    review_priority int,              -- 1 낮은 줄 남음 / 2 빈 쪽 / 3 그 밖의 OCR만 출처 쪽
    reviewer      text,
    review_status text,               -- 확인완료 / 정정함 / 확인불가
    corrected_text text,              -- 정정함일 때 사람이 고친 글자
    review_note   text,
    reviewed_at   timestamptz,
    ocred_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (rcept_no, dcm_no, page),
    FOREIGN KEY (rcept_no, dcm_no) REFERENCES raw.policy_document (rcept_no, dcm_no) ON DELETE CASCADE
);
COMMENT ON TABLE raw.policy_page_ocr IS 'PDF 쪽별 OCR 결과·신뢰도·사람 검토 (빈 쪽·실패도 1행)';
-- 정정 공시 연결: DART 원문 화면의 최초 접수번호(일반 공시는 자기 번호, 정정 공시는 처음 낸 공시 번호).
-- 같은 최초 번호 묶음에서 접수번호가 가장 늦은 것이 최신 판. 정정 전 판도 지우지 않고 이력으로 둔다
-- (source/core/policy_docs.root_rcept_no, source/scripts/link_policy_corrections.py)
ALTER TABLE raw.policy_filing ADD COLUMN IF NOT EXISTS root_rcept_no text;  -- 최초 접수번호, 모르면 비움
CREATE OR REPLACE VIEW core.v_policy_filing_latest AS
SELECT f.rcept_no, f.corp_code, f.corp_name, f.rcept_dt, f.report_nm, f.is_correction,
       coalesce(f.root_rcept_no, f.rcept_no) AS chain_root,
       max(f.rcept_no) OVER w AS latest_rcept_no,
       f.rcept_no = max(f.rcept_no) OVER w AS is_latest,
       count(*) OVER w AS n_versions
FROM raw.policy_filing f
WINDOW w AS (PARTITION BY coalesce(f.root_rcept_no, f.rcept_no));
COMMENT ON VIEW core.v_policy_filing_latest IS '정책 공시마다 같은 계획의 최신 판인지 (is_latest). 검색·검토표는 최신 판만 쓴다';

-- 주식의 총수 현황 (OpenDART stockTotqySttus, source/core/share_total.py, source/scripts/collect_share_total.py)
-- 밸류업 주당배당금 목표 → 총액 환산에 쓰는 유통주식수(발행 − 자기주식). 받은 글자(*_raw)와 숫자를 함께 둔다.
-- 값이 없거나 오류인 응답도 se='(응답 없음)' 1행으로 남겨 빠진 회사를 셀 수 있게 한다.
CREATE TABLE IF NOT EXISTS raw.dart_share_total (
    corp_code     char(8) NOT NULL,
    bsns_year     int NOT NULL,
    reprt_code    text NOT NULL,      -- 11011 사업보고서
    se            text NOT NULL,      -- 보통주 / 우선주 / 합계 등 (받은 그대로)
    share_class   text,               -- se를 묶은 것: 보통 / 우선·종류 / 합계 / 비고 / 기타 (core.share_total.share_class)
    rcept_no      text,
    stlm_dt       text,               -- 결산 기준일
    issued        numeric,            -- 발행주식총수
    treasury      numeric,            -- 자기주식수
    floating      numeric,            -- 유통주식수 (비었고 발행·자기가 있으면 발행 − 자기)
    issued_raw    text,
    treasury_raw  text,
    floating_raw  text,
    floating_note text,
    api_status    text,               -- 000 정상 / 013 데이터 없음 등
    api_message   text,
    fetched_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (corp_code, bsns_year, reprt_code, se)
);
COMMENT ON TABLE raw.dart_share_total IS '회사×사업연도×보고서×주식 종류 1행: 발행·자기·유통 주식수 (OpenDART)';
ALTER TABLE raw.dart_share_total ADD COLUMN IF NOT EXISTS share_class text;  -- share_class 추가 전에 만든 표에도 붙임

-- 주식 총수 이상치 (source/core/share_check.py, source/scripts/build_share_check.py). 원본(raw.dart_share_total)은 고치지 않는다.
-- 자본금과 1% 안에서 맞는 회사는 행을 남기지 않는다. action = 보정(factor를 곱함) / 표시만(factor 1)
CREATE TABLE IF NOT EXISTS core.core_share_check (
    corp_code   char(8) NOT NULL,
    bsns_year   int NOT NULL,
    reprt_code  text NOT NULL,
    "check"     text NOT NULL,      -- API 단위 오류(1,000배) / 자본금과 차이 / 대조 불가 / 보통주 행 없음
    action      text NOT NULL,      -- 보정 / 표시만
    factor      numeric NOT NULL,   -- 보정 배수 (1,000배 오류면 0.001)
    reason      text NOT NULL,
    ratio       numeric,            -- (보통+우선·종류+기타 발행) × 액면 ÷ 자본금
    pbr_api     numeric,            -- 종가 × 보통주 유통(API 값) ÷ 자본총계
    pbr_fixed   numeric,            -- 같은 식, ÷1,000 한 값
    issued_all  numeric,
    par_won     numeric,
    capital_won numeric,
    close_won   numeric,
    equity_won  numeric,
    rule        text NOT NULL,
    checked_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (corp_code, bsns_year, reprt_code)
);
COMMENT ON TABLE core.core_share_check IS '주식 총수 이상치와 사유·보정 배수 (자본금·PBR 대조). 정상 회사는 행 없음';

-- 회사×사업연도 보통주 1행: API 값과 보정값·사유를 나란히. 보통주 행이 없는 회사는 core_share_check에만 있음
CREATE OR REPLACE VIEW core.v_share_total_checked AS
SELECT s.corp_code, c.corp_name, s.bsns_year, s.reprt_code, s.stlm_dt, s.rcept_no,
       s.issued AS issued_api, s.treasury AS treasury_api, s.floating AS floating_api,
       s.issued * coalesce(k.factor, 1) AS issued,
       s.treasury * coalesce(k.factor, 1) AS treasury,
       s.floating * coalesce(k.factor, 1) AS floating,
       coalesce(k."check", '자본금 일치') AS "check",
       coalesce(k.action, '그대로') AS action,
       k.factor, k.reason, k.ratio, k.pbr_api, k.pbr_fixed
FROM raw.dart_share_total s
JOIN core.core_company c USING (corp_code)
LEFT JOIN core.core_share_check k USING (corp_code, bsns_year, reprt_code)
WHERE s.share_class = '보통';
COMMENT ON VIEW core.v_share_total_checked IS '보통주 발행·자기·유통 주식수: API 값(*_api)과 보정값, 이상치 사유';

-- 4층 배당 정책 상세 (P1): 자사주 매입·소각, 투자·인수 공시 (source/core/policy_filings.py, source/scripts/collect_policy_filings.py)
-- 값은 OpenDART 주요사항보고서 API 원문 글자 그대로. API가 없는 공시(주식소각결정 등)는 raw.dart_filing_list 제목만(api = 'filing_list').
-- 점수·평가는 붙이지 않는다. 자회사·종속회사의 주요경영사항 공시는 넣지 않는다.
CREATE TABLE IF NOT EXISTS raw.dart_policy_filing (
    api               text NOT NULL,      -- tsstkAqDecsn 등 API 이름, 또는 filing_list
    rcept_no          text NOT NULL,      -- 접수번호
    corp_code         char(8) NOT NULL,
    corp_name         text,
    kind              text NOT NULL,      -- 자기주식 취득 / 자기주식 처분 / 자기주식 취득 신탁 체결·해지 / 타법인 주식 양수 / 주식 소각 등
    report_nm         text,               -- 공시 제목 (raw.dart_filing_list)
    decision_date_raw text,               -- 결정일·이사회결의일 원문 (예: 2026년 01월 28일)
    amount_raw        text,               -- 금액 원문(원): 취득·처분 예정금액 보통주, 신탁 계약금액, 양수금액
    amount_etc_raw    text,               -- 기타주식 금액 원문
    shares_raw        text,               -- 주식수 원문: 보통주(자기주식), 양수주식수(타법인)
    shares_etc_raw    text,               -- 기타주식 주식수 원문
    purpose_raw       text,               -- 목적 원문
    target_raw        text,               -- 대상 원문: 취득방법·계약기관·발행회사·자산명
    period_bgn_raw    text,               -- 예정기간 시작 원문
    period_end_raw    text,               -- 예정기간 끝·양수예정일자 원문
    source            text NOT NULL,      -- OpenDART <api> / raw.dart_filing_list (제목만)
    item              jsonb,              -- API 응답 한 건 전체
    fetched_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (api, rcept_no)
);
COMMENT ON TABLE raw.dart_policy_filing IS '자사주 취득·처분·신탁·소각, 타법인·영업·유형자산 양수, 시설투자 공시 원문 값 (시연 10개사, 2024~)';

-- 화면용: 숫자·날짜로 읽고 원문 링크를 붙인다. 금액 = 보통주 + 기타주식 (둘 다 비면 비움)
CREATE OR REPLACE VIEW core.v_policy_filing AS
WITH n AS (
    SELECT p.*,
           CASE WHEN replace(amount_raw, ',', '') ~ '^-?[0-9]+(\.[0-9]+)?$' THEN replace(amount_raw, ',', '')::numeric END AS amt,
           CASE WHEN replace(amount_etc_raw, ',', '') ~ '^-?[0-9]+(\.[0-9]+)?$' THEN replace(amount_etc_raw, ',', '')::numeric END AS amt_etc,
           CASE WHEN replace(shares_raw, ',', '') ~ '^[0-9]+$' THEN replace(shares_raw, ',', '')::numeric END AS sh,
           CASE WHEN replace(shares_etc_raw, ',', '') ~ '^[0-9]+$' THEN replace(shares_etc_raw, ',', '')::numeric END AS sh_etc,
           regexp_match(decision_date_raw, '([0-9]{4})\D+([0-9]{1,2})\D+([0-9]{1,2})') AS d
    FROM raw.dart_policy_filing p
)
SELECT corp_code, corp_name, rcept_no, to_date(left(rcept_no, 8), 'YYYYMMDD') AS rcept_dt,
       CASE WHEN d IS NOT NULL THEN make_date(d[1]::int, d[2]::int, d[3]::int) END AS decision_date,
       kind, report_nm,
       CASE WHEN amt IS NULL AND amt_etc IS NULL THEN NULL ELSE coalesce(amt, 0) + coalesce(amt_etc, 0) END AS amount_won,
       CASE WHEN sh IS NULL AND sh_etc IS NULL THEN NULL ELSE coalesce(sh, 0) + coalesce(sh_etc, 0) END AS shares,
       purpose_raw AS purpose, target_raw AS target, period_bgn_raw, period_end_raw,
       coalesce(report_nm, '') LIKE '[%정정]%' AS is_correction,
       api, source, 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=' || rcept_no AS url
FROM n;
COMMENT ON VIEW core.v_policy_filing IS '배당과 경합하는 현금 사용 공시(자사주·투자·인수): 날짜·종류·금액·목적·원문 링크. 점수 없음';

-- 최대주주 현황 (OpenDART hyslrSttus, source/scripts/collect_major_holder.py). 받은 그대로 1행씩. 값이 없는 회사도 1행(nm = '(응답 없음)')
CREATE TABLE IF NOT EXISTS raw.dart_major_holder (
    corp_code         char(8) NOT NULL,
    bsns_year         int NOT NULL,
    reprt_code        text NOT NULL,      -- 11011 사업보고서
    seq               int NOT NULL,       -- 응답 안 순서 (같은 이름이 주식 종류별로 여러 행)
    rcept_no          text,
    stlm_dt           text,
    nm                text,               -- 성명 (받은 그대로, '계' = 합계 행)
    relate            text,               -- 관계 (최대주주 본인 / 특수관계인 등)
    stock_knd         text,               -- 주식 종류 (받은 그대로)
    share_class       text,               -- 보통 / 우선·종류 / 합계 / 비고 / 기타 (core.share_total.share_class)
    bsis_shares       numeric,            -- 기초 소유 주식수
    bsis_pct          numeric,            -- 기초 지분율(%)
    trmend_shares     numeric,            -- 기말 소유 주식수
    trmend_pct        numeric,            -- 기말 지분율(%)
    bsis_shares_raw   text,
    bsis_pct_raw      text,
    trmend_shares_raw text,
    trmend_pct_raw    text,
    rm                text,               -- 비고
    api_status        text,               -- 000 정상 / 013 데이터 없음 등
    api_message       text,
    fetched_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (corp_code, bsns_year, reprt_code, seq)
);
COMMENT ON TABLE raw.dart_major_holder IS '회사×사업연도×보고서 최대주주·특수관계인 1행씩 (OpenDART 최대주주 현황, 원문 그대로)';

-- 회사별 최대주주+특수관계인 보통주 지분율 합계와 최대주주 종류 (source/core/major_holder.py). 이름은 두지 않는다
CREATE TABLE IF NOT EXISTS core.core_major_holder (
    corp_code    char(8) NOT NULL,
    bsns_year    int NOT NULL,
    reprt_code   text NOT NULL,
    pct_common   numeric,            -- 최대주주+특수관계인 보통주 기말 지분율(%)
    pct_source   text NOT NULL,      -- '계' 행 / 행 합계 / 자료 없음
    largest_kind text,               -- 개인 / 법인 / 판단 불가
    largest_rule text,               -- 관계 칸 / 지분 가장 큰 행
    n_rows       int NOT NULL,       -- 보통주 행 수('계' 제외)
    api_status   text,
    rule         text NOT NULL,
    built_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (corp_code, bsns_year, reprt_code)
);
COMMENT ON TABLE core.core_major_holder IS '최대주주+특수관계인 보통주 지분율 합계·최대주주 개인/법인 (점수 없음, 이름 없음)';

-- ---------------------------------------------------------------- partner
-- 다른 팀(4조참치)이 준 자료 (data/partner/4조참치_20261030, source/scripts/load_partner.py). raw·core와 섞지 않는다.
-- grp = 대조군(우리 638사 밖, 분석용) · 겹침(우리 638사와 겹침, 우리 값이 더 정확하므로 대조용만).
-- *_status: 값 있음 / 원문에 없음 / 실재하지만 불러올 수 없음, *_reason에 근거. 다시 적재하면 partner 표만 비우고 새로 채운다.
CREATE SCHEMA IF NOT EXISTS partner;

CREATE TABLE IF NOT EXISTS partner.company (
    corp_code       char(8) PRIMARY KEY,
    grp             text NOT NULL,      -- 대조군 / 겹침
    corp_name       text NOT NULL,
    stock_code      text,
    corp_cls        text,               -- Y 유가 · K 코스닥 · N 코넥스 · E 기타
    market          text,
    listed_now      text,               -- 4조 확인 시점 Y/N
    delist_date     text,
    delist_reason   text,
    fiscal_month    int,
    industry        text NOT NULL,      -- 4조 업종 (제조업 · 도소매업 · 건설업 · 부동산임대업)
    ksic_code       text,
    ksic_name       text,
    classify_method text,
    classify_reason text,
    induty_code     text,               -- OpenDART 기업개황 업종코드
    est_dt          text,
    source          text NOT NULL
);
COMMENT ON TABLE partner.company IS '4조 수집 대상 회사 1곳. grp로 대조군·겹침 구분';

CREATE TABLE IF NOT EXISTS partner.report (
    rcept_no       text PRIMARY KEY,
    corp_code      char(8) NOT NULL,
    period         text NOT NULL,       -- YYYY.MM
    bsns_year      int NOT NULL,
    report_nm      text,
    rcept_dt       text,
    version        text,                -- 최초 · 기재정정 · 첨부정정 · 첨부추가
    is_first       boolean,
    is_latest_full boolean,             -- 결산기 최신 전체본 (분석에는 이것만)
    doc_status     text NOT NULL,       -- 받음 / 실재하지만 불러올 수 없음
    api_status     text,
    notes_sections int
);
COMMENT ON TABLE partner.report IS '4조가 받은(또는 못 받은) 사업보고서 1건 (2015 회계연도 이후 모든 버전)';

CREATE TABLE IF NOT EXISTS partner.financial_year (
    corp_code          char(8) NOT NULL,
    bsns_year          int NOT NULL,
    fs_basis           text,            -- 연결 / 별도 (연결 우선)
    ni_owner_won       numeric,         -- 지배주주 순이익 (별도만 있으면 당기순이익)
    ni_status          text NOT NULL,
    ni_reason          text,
    liabilities_won    numeric,
    liabilities_status text NOT NULL,
    liabilities_reason text,
    equity_won         numeric,
    equity_status      text NOT NULL,
    equity_reason      text,
    assets_won         numeric,
    assets_status      text NOT NULL,
    assets_reason      text,
    source_rcept_no    text,            -- 값을 준 사업보고서
    source_column      text,            -- 당기 / 전기 / 전전기
    report_rcept_no    text,            -- 그 사업연도 사업보고서
    PRIMARY KEY (corp_code, bsns_year)
);
COMMENT ON TABLE partner.financial_year IS '회사×사업연도 지배주주 순이익·부채·자본·자산 (OpenDART 재무제표, 원 단위). core.core_financial_year와 같은 열 이름';

CREATE TABLE IF NOT EXISTS partner.dividend_year (
    corp_code           char(8) NOT NULL,
    bsns_year           int NOT NULL,
    d_won               numeric,        -- 현금배당총액 D (원문 백만 원 × 1,000,000)
    d_mil_raw           numeric,        -- 원문 표 값(백만 원)
    d_status            text NOT NULL,
    d_reason            text,
    dps_common_won      numeric,        -- 보통주 주당 현금배당금
    dps_status          text NOT NULL,
    dps_reason          text,
    div_source_rcept_no text,
    div_source_column   text,
    cf_paid_won         numeric,        -- 현금흐름표 배당금 지급 (양수)
    cf_status           text NOT NULL,
    cf_reason           text,
    cf_accounts         text,
    nci_paid_won        numeric,        -- 비지배지분 배당 (참고)
    cf_fs_basis         text,
    cf_source_rcept_no  text,
    cf_source_column    text,
    PRIMARY KEY (corp_code, bsns_year)
);
COMMENT ON TABLE partner.dividend_year IS '회사×사업연도 D·보통주 DPS(사업보고서 배당 표)와 현금흐름표 배당금 지급. core.core_dividend_year와 같은 열 이름';

CREATE TABLE IF NOT EXISTS partner.dividend_item (
    corp_code     char(8) NOT NULL,
    bsns_year     int NOT NULL,         -- 그 열이 가리키는 사업연도
    rcept_no      text NOT NULL,
    report_column text NOT NULL,        -- 당기 / 전기 / 전전기
    item          text NOT NULL,        -- 원문 '구분' 글자
    stock_kind    text,                 -- 원문 '주식의 종류' 글자 (없으면 -)
    value         text,                 -- 원문 글자 그대로
    value_num     numeric
);
COMMENT ON TABLE partner.dividend_item IS '사업보고서 배당 표 1칸 (결산기 최신 전체본, 2017~2025). raw.dart_dividend_item과 같은 모양';
CREATE INDEX IF NOT EXISTS partner_dividend_item_corp_year ON partner.dividend_item (corp_code, bsns_year);

CREATE TABLE IF NOT EXISTS partner.share_total (
    corp_code      char(8) NOT NULL,
    bsns_year      int NOT NULL,
    rcept_no       text NOT NULL,
    se             text,                -- 주식 종류 (원문 그대로)
    share_class    text,                -- 보통 / 우선·종류 / 합계 / 기타 (core.share_total.share_class)
    stlm_dt        text,                -- 표 기준일 YYYYMMDD
    authorized     numeric,             -- Ⅰ 발행할 주식의 총수
    ever_issued    numeric,             -- Ⅱ 현재까지 발행한 주식의 총수
    decreased      numeric,             -- Ⅲ 현재까지 감소한 주식의 총수
    reduced        numeric,             -- 1. 감자
    retired        numeric,             -- 2. 이익소각
    redeemed       numeric,             -- 3. 상환주식의 상환
    other_decrease numeric,             -- 4. 기타
    issued         numeric,             -- Ⅳ 발행주식의 총수
    treasury       numeric,             -- Ⅴ 자기주식수
    floating       numeric,             -- Ⅵ 유통주식수
    treasury_pct   numeric,             -- Ⅶ 자기주식 보유비율(%)
    unit_text      text,                -- 원문 기준일·단위 글자
    unit_factor    numeric,             -- 주식수에 곱한 값 (천주 1000 · 백만주 1000000)
    extra          text,
    note           text,
    status         text NOT NULL,
    reason         text
);
COMMENT ON TABLE partner.share_total IS '사업보고서 주식의 총수 표: 보고서×주식 종류 1행. 주식수는 주 단위로 맞춤. raw.dart_share_total과 같은 열 이름';
CREATE INDEX IF NOT EXISTS partner_share_total_corp_year ON partner.share_total (corp_code, bsns_year);

CREATE TABLE IF NOT EXISTS partner.major_holder (
    corp_code     char(8) NOT NULL,
    bsns_year     int NOT NULL,
    rcept_no      text NOT NULL,
    seq           int,                  -- 표 안 순서
    stlm_dt       text,
    nm            text,                 -- 성명 ('계' = 합계 행)
    relate        text,
    stock_knd     text,
    share_class   text,
    bsis_shares   numeric,
    bsis_pct      numeric,
    trmend_shares numeric,
    trmend_pct    numeric,
    rm            text,
    is_total      boolean,
    unit_text     text,
    unit_factor   numeric,
    status        text NOT NULL,
    reason        text
);
COMMENT ON TABLE partner.major_holder IS '사업보고서 최대주주·특수관계인 1행. 주식수는 주 단위로 맞춤. raw.dart_major_holder와 같은 열 이름';
CREATE INDEX IF NOT EXISTS partner_major_holder_corp_year ON partner.major_holder (corp_code, bsns_year);

CREATE TABLE IF NOT EXISTS partner.fs_line (
    corp_code         char(8) NOT NULL,
    bsns_year         int NOT NULL,
    fs_div            text NOT NULL,    -- CFS / OFS
    sj_div            text NOT NULL,    -- BS · IS · CIS · CF · SCE
    sj_nm             text,
    ord               int,
    account_id        text,
    account_nm        text,
    account_detail    text,
    thstrm_nm         text,
    thstrm_amount     numeric,
    frmtrm_nm         text,
    frmtrm_amount     numeric,
    bfefrmtrm_nm      text,
    bfefrmtrm_amount  numeric,
    thstrm_add_amount numeric,
    currency          text,
    rcept_no          text
);
COMMENT ON TABLE partner.fs_line IS 'OpenDART 단일회사 전체 재무제표 1줄 (4조 fnltt, 원 단위 그대로)';
CREATE INDEX IF NOT EXISTS partner_fs_line_corp_year ON partner.fs_line (corp_code, bsns_year, fs_div, sj_div);

CREATE TABLE IF NOT EXISTS partner.filing (
    corp_code  char(8) NOT NULL,
    pblntf_ty  text NOT NULL,           -- A 정기공시 · B 주요사항보고 · I 거래소공시
    rcept_no   text NOT NULL,
    rcept_dt   date,
    report_nm  text,
    flr_nm     text,
    rm         text,
    corp_cls   text,
    PRIMARY KEY (corp_code, pblntf_ty, rcept_no)
);
COMMENT ON TABLE partner.filing IS '4조가 받은 OpenDART 공시 목록 1건 (2015-01 이후). 배당 결정 공시는 report_nm에 배당결정';

CREATE TABLE IF NOT EXISTS partner.risk_event (
    corp_code        char(8) NOT NULL,
    event_type       text,
    severity         text,               -- 4조 잠정값
    use              text,
    is_first_of_type text,
    event_date       text,
    date_basis       text,
    fiscal_period    text,
    rcept_no         text,
    title            text,
    raw              jsonb NOT NULL      -- 4조 risk_events.csv 한 행 그대로
);
COMMENT ON TABLE partner.risk_event IS '4조가 모은 상환·연체 위험 사건 후보 (라벨 후보, 원문 대조 전)';

CREATE TABLE IF NOT EXISTS partner.audit_opinion (
    corp_code     char(8) NOT NULL,
    source        text NOT NULL,         -- 원문 (audit_from_documents) / API (audit_api)
    fiscal_period text,
    rcept_no      text,
    fs            text,
    auditor       text,
    opinion       text,
    going_concern text,
    raw           jsonb NOT NULL
);
COMMENT ON TABLE partner.audit_opinion IS '4조가 읽은 감사의견·계속기업 불확실성 (사업보고서 원문 · OpenDART 감사의견 API)';

-- 우리 638사(확정 값)와 4조 대조군을 회사×사업연도 한 표로. 겹치는 회사는 우리 값만 (같은 회사가 두 번 나오지 않음)
CREATE OR REPLACE VIEW partner.v_panel AS
WITH ours AS (
    SELECT coalesce(f.corp_code, d.corp_code) AS corp_code, coalesce(f.bsns_year, d.bsns_year) AS bsns_year,
           f.fs_basis, f.ni_owner_won, f.liabilities_won, f.equity_won,
           d.d_dart_won AS d_won, d.dps_common_won, d.cf_paid_won_verified AS cf_paid_won
    FROM core.v_financial_year_verified f
    FULL JOIN core.v_dividend_year_verified d USING (corp_code, bsns_year))
SELECT '우리 638사'::text AS source, o.corp_code, c.corp_name, c.stock_code, c.market, pc.industry AS industry_4jo,
       o.bsns_year, o.fs_basis, o.ni_owner_won, o.liabilities_won, o.equity_won, NULL::numeric AS assets_won,
       o.d_won, o.dps_common_won, o.cf_paid_won,
       CASE WHEN o.ni_owner_won IS NULL THEN '빈칸' ELSE '확정' END AS ni_status,
       CASE WHEN o.liabilities_won IS NULL THEN '빈칸' ELSE '확정' END AS liabilities_status,
       CASE WHEN o.equity_won IS NULL THEN '빈칸' ELSE '확정' END AS equity_status,
       NULL::text AS assets_status,
       CASE WHEN o.d_won IS NULL THEN '빈칸' ELSE '확정' END AS d_status,
       CASE WHEN o.dps_common_won IS NULL THEN '빈칸' ELSE '확정' END AS dps_status,
       CASE WHEN o.cf_paid_won IS NULL THEN '빈칸' ELSE '확정' END AS cf_status,
       NULL::text AS ni_reason, NULL::text AS d_reason
FROM ours o
JOIN core.core_company c USING (corp_code)
LEFT JOIN partner.company pc USING (corp_code)
UNION ALL
SELECT '4조 대조군', pc.corp_code, pc.corp_name, pc.stock_code, pc.market, pc.industry,
       f.bsns_year, f.fs_basis, f.ni_owner_won, f.liabilities_won, f.equity_won, f.assets_won,
       d.d_won, d.dps_common_won, d.cf_paid_won,
       f.ni_status, f.liabilities_status, f.equity_status, f.assets_status, d.d_status, d.dps_status, d.cf_status,
       f.ni_reason, d.d_reason
FROM partner.company pc
JOIN partner.financial_year f USING (corp_code)
LEFT JOIN partner.dividend_year d USING (corp_code, bsns_year)
WHERE pc.grp = '대조군';
COMMENT ON VIEW partner.v_panel IS
    '분석용 회사×사업연도: 우리 638사(core 확정 값, 2017~2026) + 4조 대조군(partner, 2017~2025, 4개 업종). '
    '*_status: 우리는 확정/빈칸, 4조는 값 있음/원문에 없음/실재하지만 불러올 수 없음 — 분석에는 확정·값 있음만. '
    'D 기준 차이: 우리는 다음 해 보고서가 고쳐 적은 값을 쓴 해가 있고 4조는 그 해 보고서 당기 칸. industry_4jo는 4조 분류(우리 회사는 겹칠 때만). '
    '4조 D가 원문에 없음이고 d_reason이 ''원문 배당 표 값 ''-'''' 이면 무배당(0)으로 볼 수 있음';

CREATE TABLE IF NOT EXISTS partner.krx_price_daily (
    corp_code  char(8) NOT NULL,
    trade_date date NOT NULL,
    close_adj  numeric NOT NULL,     -- 수정 종가(원)
    volume     bigint,
    source     text NOT NULL,
    PRIMARY KEY (corp_code, trade_date)
);
COMMENT ON TABLE partner.krx_price_daily IS
    '4조 대조군 상장사 회사×거래일 수정 종가 (source/scripts/collect_partner_prices.py, 네이버 금융 차트). '
    '우리 638사 KRX 수정 종가(raw.krx_price_daily)와 표본 8개사 모든 거래일 같음. 상장폐지·비상장 회사는 없음';

-- 배당과 거시지표의 상관 (source/scripts/analyze_macro_dividend.py, 2026-11-02). 순열검정이 오래 걸려 화면은 저장한 결과만 읽는다
CREATE TABLE IF NOT EXISTS core.core_macro_dividend_year (
    year      int NOT NULL,
    item      text NOT NULL,        -- source/core/macro_dividend.py 열 이름 (payer_share, base_rate, current_account_chg 등)
    value     double precision,
    built_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (year, item)
);
COMMENT ON TABLE core.core_macro_dividend_year IS '사업연도×항목 1행: 연도별 배당 지표와 같은 해 거시지표 (데이터 분석 화면 거시지표 탭)';

CREATE TABLE IF NOT EXISTS core.core_macro_dividend_corr (
    lag             text NOT NULL,  -- same / prev / decision
    kind            text NOT NULL,  -- level / diff / panel / panel_ex2025
    dividend        text NOT NULL,
    macro           text NOT NULL,
    dividend_label  text NOT NULL,
    macro_label     text NOT NULL,
    n               int,            -- 연도 갈래: 연도 수
    rows            int,            -- 회사×연도 갈래: 행 수
    spearman        double precision,
    p               double precision, -- 순열검정 (회사×연도는 연도 단위로 섞음)
    built_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (lag, kind, dividend, macro)
);
COMMENT ON TABLE core.core_macro_dividend_corr IS '시차×갈래×배당 지표×거시 변수 1행 Spearman 상관과 p값';

-- 화면용 분석 결과 (source/scripts/analyze_panel.py). 분석이 1~2분 걸려 API는 저장한 값만 읽는다
CREATE TABLE IF NOT EXISTS partner.analysis_result (
    key      text PRIMARY KEY,          -- panel = 우리 638사 vs 대조군 비교
    payload  jsonb NOT NULL,
    built_at timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE partner.analysis_result IS '데이터 이야기 화면이 읽는 대조군 비교 결과 (report/분석/대조군_비교분석_*.md와 같은 숫자)';

-- 회사 행동 분석 (source/scripts/analyze_exposure_dividend.py · source/scripts/analyze_policy_did.py, 2026-11-02).
-- 순열검정이 오래 걸려 화면은 저장한 결과만 읽는다 (source/core/behavior_data.py)
CREATE TABLE IF NOT EXISTS core.core_behavior_fit (
    analysis    text NOT NULL,      -- exposure = 금리·환율 노출도 / policy = 분리과세 이중차분
    name        text NOT NULL,      -- 검정 이름 (결과 문서의 표와 같음)
    role        text NOT NULL,      -- primary(미리 정한 주 검정) / robust(보조) / placebo(가짜 제도 해)
    coef        double precision,
    low         double precision,   -- 95% 범위 (회사 단위 묶음 표준오차)
    high        double precision,
    p_cluster   double precision,
    p_perm      double precision,   -- 순열검정 (노출도: 연도 섞기, 제도: 무리 섞기)
    p_holm      double precision,   -- 주 검정끼리 Holm 보정
    n           int,
    n_firms     int,
    n_treated   int,                -- 제도: 2025년 처리 무리 회사 수
    built_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (analysis, name)
);
COMMENT ON TABLE core.core_behavior_fit IS '회사×연도 패널 회귀 검정 1행 (report/분석/배당_노출도_분석_결과.md, report/분석/배당_제도효과_분석_결과.md와 같은 숫자)';

CREATE TABLE IF NOT EXISTS core.core_behavior_series (
    analysis    text NOT NULL,
    series      text NOT NULL,      -- es_holder·es_close(해마다 계수) / rate_holder·rate_close(무리별 비율 %) / tercile_up·tercile_cut
    label       text NOT NULL,      -- 무리 이름 (계수 줄은 '계수')
    year        int NOT NULL,       -- 사업연도 (연도가 없는 줄은 0)
    value       double precision,
    low         double precision,
    high        double precision,
    n           int,
    built_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (analysis, series, label, year)
);
COMMENT ON TABLE core.core_behavior_series IS '회사 행동 분석의 그림용 줄: 해마다 계수와 95% 범위, 무리별 단순 비율';

-- 고배당기업 638곳의 상장 우선주 (source/scripts/collect_pref_stocks.py, 2026-11-02). 원천 엑셀 07의 상장우선주 코드 칸이 비어 있어 새로 받음
CREATE TABLE IF NOT EXISTS raw.krx_pref_stock (
    corp_code        char(8) NOT NULL,
    pref_code        text NOT NULL,      -- 우선주 종목코드 (보통주 코드 앞 5자리 + 끝 한 글자)
    pref_name        text NOT NULL,      -- 예: 삼성전자우, 현대차2우B, CJ4우(전환)
    last_trade_date  date,
    status           text NOT NULL,      -- 상장 중 / 거래 없음(상장폐지 추정)
    source           text NOT NULL,
    fetched_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (corp_code, pref_code)
);
COMMENT ON TABLE raw.krx_pref_stock IS '고배당기업 우선주 종목 1행. 네이버 금융 차트에 후보 코드를 물어 종목명이 우선주 모양인 것만 (source/scripts/collect_pref_stocks.py)';

-- 배당 결정 공시 아래 '종류주식에 대한 배당 관련 사항' 표 (source/scripts/collect_pref_dividend_class.py, 2026-11-02)
CREATE TABLE IF NOT EXISTS raw.dividend_decision_class (
    rcept_no    text NOT NULL,
    corp_code   char(8) NOT NULL,
    class_name  text NOT NULL,      -- 공시에 적힌 종류주식명 (예: 두산2우B, 우선주)
    class_kind  text NOT NULL,      -- 종류주식구분 (예: 종류주식, 1우선주, 2우선주)
    dps_won     numeric NOT NULL,   -- 1주당 배당금(원)
    total_won   numeric,
    fetched_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (rcept_no, class_name, class_kind)
);
COMMENT ON TABLE raw.dividend_decision_class IS '배당 결정 공시의 우선주 종목별 1주당 배당금. raw.dividend_decision은 종류주식 한 칸만 담아 종목을 가르지 못함';
