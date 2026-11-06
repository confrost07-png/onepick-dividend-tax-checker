-- 원픽 · 내 담당 작업 결과를 SQL로 다시 확인 (데이터: data/sample/*.csv, 원본 DB에서 추출)
-- 실행: python sql/run_sql.py

-- [1] 재무값 전수 검산: 검토 구분별 칸 수 (메모 맨 앞 [구분] 기준)
SELECT CASE
         WHEN memo LIKE '[자동 대조]%'      THEN '1. 자동 대조 일치'
         WHEN memo LIKE '[원문 직접 판독]%' THEN '2. 원문 직접 판독'
         ELSE '3. DB 정정'
       END                         AS 구분,
       COUNT(*)                    AS 칸수,
       COUNT(DISTINCT corp_code)   AS 회사수
FROM review_values
GROUP BY 1
ORDER BY 1;

-- [2] DB 정정 197칸: 항목별 · 정정 사유별
SELECT CASE item WHEN 'equity_won' THEN '자본총계' WHEN 'liabilities_won' THEN '부채총계' ELSE '지배주주순이익' END AS 항목,
       SUBSTR(memo, 2, INSTR(memo, ']') - 2)     AS 정정_사유,
       COUNT(*)                                  AS 칸수
FROM review_values
WHERE status = '정정됨(배제)'
GROUP BY 1, 2
ORDER BY 3 DESC;

-- [3] 638사 판정 결과
SELECT status AS 판정, COUNT(*) AS 회사수
FROM judgement
GROUP BY 1
ORDER BY 2 DESC;

-- [4] 시세 수집 현황 (사용 가능 / 주의 / 제외 거래일)
SELECT coverage            AS 수집,
       COUNT(*)            AS 회사수,
       SUM(days)           AS 거래일_합,
       SUM(ok_days)        AS 사용가능,
       SUM(caution_days)   AS 주의,
       SUM(excluded_days)  AS 제외
FROM price_coverage
GROUP BY 1;
