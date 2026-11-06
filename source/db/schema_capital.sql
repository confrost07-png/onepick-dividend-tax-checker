-- 증자·감자·액면분할·병합 공시 (source/scripts/load_capital.py, source/core/dart_capital.py)
-- 회사 목록은 core.core_company, 기간은 배당 결정 공시(05)와 같은 2023-01-01 ~ 2026-10-20.
-- 원천 응답은 payload(jsonb)에 그대로 두고, 자주 쓰는 칸만 열로 꺼낸다. 원천에서 다시 만들 수 있어 매번 비우고 다시 채운다.

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS core;

CREATE TABLE IF NOT EXISTS raw.dart_filing_list (
    rcept_no    text PRIMARY KEY,
    corp_code   char(8) NOT NULL,
    corp_name   text,
    stock_code  text,
    corp_cls    text,               -- Y 유가증권 / K 코스닥 / N 코넥스 / E 기타
    pblntf_ty   text NOT NULL,      -- B 주요사항보고 / I 거래소공시
    report_nm   text,
    flr_nm      text,               -- 제출인
    rcept_dt    date,
    rm          text,               -- 비고 (유: 유가증권시장본부 소관 등)
    source      text NOT NULL
);
COMMENT ON TABLE raw.dart_filing_list IS '공시 목록 1건 (OpenDART list.json, 주요사항보고·거래소공시). 증자·감자·분할·병합을 고르는 바탕';
CREATE INDEX IF NOT EXISTS dart_filing_list_corp ON raw.dart_filing_list (corp_code, rcept_dt);

CREATE TABLE IF NOT EXISTS raw.dart_capital_event (
    rcept_no         text NOT NULL,
    kind             text NOT NULL,     -- 유상증자 / 무상증자 / 유무상증자(유상) / 유무상증자(무상) / 감자
    corp_code        char(8) NOT NULL,
    corp_name        text,
    rcept_dt         date,
    report_nm        text,
    is_correction    boolean,           -- 보고서명이 [기재정정] 등으로 시작
    version          text NOT NULL,     -- API 최종본 / 원문 최종본(API에 없어 DART 원문에서 읽음) / 앞선 판(값 없음) / 첨부만 정정 / API 응답 없음
    shares_common    numeric,           -- 신주(증자) 또는 감자하는 보통주식 수
    shares_pref      numeric,           -- 같은 기준의 기타·종류주식 수
    par_won          numeric,           -- 1주당 액면가액(원)
    before_common    numeric,           -- 증자·감자 전 발행주식총수(보통)
    before_pref      numeric,
    after_common     numeric,           -- 감자 후 발행주식총수(보통). 증자는 비움
    after_pref       numeric,
    per_share_common numeric,           -- 무상: 1주당 신주배정 주식수(보통)
    per_share_pref   numeric,
    funds_won        numeric,           -- 유상: 자금조달 목적별 금액 합계(원)
    capital_before_won numeric,         -- 감자 전 자본금(원)
    capital_after_won  numeric,         -- 감자 후 자본금(원)
    ratio_common_pct numeric,           -- 감자비율(보통, %)
    ratio_pref_pct   numeric,
    method           text,              -- 증자방식 / 감자방법
    reason           text,              -- 감자사유
    record_date      text,              -- 무상: 신주배정기준일, 감자: 감자기준일 (원문 그대로)
    listing_date     text,              -- 신주 상장 예정일 (원문 그대로)
    board_date       text,              -- 이사회결의일 (원문 그대로)
    check_result     text,              -- 감자: 감자 전 − 감자 주식 = 감자 후 검산
    payload          jsonb NOT NULL,    -- OpenDART 응답 1행 그대로
    link             text,
    source           text NOT NULL,     -- 응답한 API 이름
    PRIMARY KEY (rcept_no, kind)
);
COMMENT ON TABLE raw.dart_capital_event IS '증자·감자 결정 공시 1건(유무상은 유상·무상 2행) (OpenDART 주요사항보고서 API). API는 정정 묶음의 최종본만 주며, 앞선 판은 값 없이 목록 정보만 둠. 분석은 version이 ''API 최종본''·''원문 최종본''인 행만 씀';
ALTER TABLE raw.dart_capital_event ADD COLUMN IF NOT EXISTS version text;  -- 처음 만든 표에는 없던 열
CREATE INDEX IF NOT EXISTS dart_capital_event_corp ON raw.dart_capital_event (corp_code, rcept_dt);

CREATE TABLE IF NOT EXISTS raw.dart_split_merge (
    rcept_no      text PRIMARY KEY,
    kind          text NOT NULL,        -- 주식분할 / 주식병합
    corp_code     char(8) NOT NULL,
    corp_name     text,
    rcept_dt      date,
    report_nm     text,
    is_correction boolean,
    par_before_won numeric,             -- 1주당 가액(원) 변경 전
    par_after_won  numeric,
    shares_before_common numeric,       -- 발행주식총수 보통주식 변경 전
    shares_after_common  numeric,
    shares_before_pref   numeric,
    shares_after_pref    numeric,
    agm_date      text,                 -- 주주총회 예정일 (원문 그대로)
    effective_date text,                -- 신주의 효력발생일
    halt_start    text,                 -- 매매거래 정지기간 시작
    halt_end      text,
    listing_date  text,                 -- 신주권 상장 예정일
    board_date    text,                 -- 이사회결의일(결정일)
    purpose       text,
    check_result  text,                 -- 액면가 비율 ↔ 주식 수 비율 검산
    status        text NOT NULL,        -- 읽음 / 확인 필요 / 원문 못 받음
    link          text,
    source        text NOT NULL
);
COMMENT ON TABLE raw.dart_split_merge IS '주식분할·병합 결정 공시 1건 (DART 원문 표를 읽음, 전용 API 없음). 정정공시는 정정 후 본문을 읽음';

CREATE TABLE IF NOT EXISTS raw.dart_capital_fetch_log (
    corp_code  char(8) NOT NULL,
    step       text NOT NULL,           -- list:B / list:I / piicDecsn / fricDecsn / pifricDecsn / crDecsn / doc:<접수번호>
    result     text NOT NULL,           -- 성공 / 공시 없음 / 실패
    n_rows     int NOT NULL,
    message    text,
    PRIMARY KEY (corp_code, step)
);
COMMENT ON TABLE raw.dart_capital_fetch_log IS '회사×조회 1건 결과. 받지 못한 회사·공시를 찾는 표';

-- 같은 회사에서 감자와 주식병합·분할이 90일 안에 함께 나온 경우. 같은 일을 두 번 세지 않게 표시만 한다.
CREATE OR REPLACE VIEW core.v_split_merge_with_reduction AS
SELECT s.rcept_no, s.kind, s.corp_code, s.corp_name, s.rcept_dt,
       c.rcept_no AS reduction_rcept_no, c.rcept_dt AS reduction_rcept_dt, c.method AS reduction_method
FROM raw.dart_split_merge s
JOIN raw.dart_capital_event c
  ON c.corp_code = s.corp_code AND c.kind = '감자' AND c.version IN ('API 최종본', '원문 최종본') AND abs(c.rcept_dt - s.rcept_dt) <= 90;
COMMENT ON VIEW core.v_split_merge_with_reduction IS '분할·병합 공시와 90일 안의 같은 회사 감자 공시 짝';
