> **GitHub 포트폴리오 안내** — 이 문서는 팀 제출 당시 코드 저장소의 원본 README입니다. 폴더 경로(`report/`, `data/db/` 등)는 팀 저장소 기준이라 이 포트폴리오 저장소의 구조와 다를 수 있습니다. 포트폴리오 요약은 맨 위 [`README.md`](../README.md)를 보세요.

# FINAL_PROJECT_ONE_PICK

**원픽(ONE PICK) · 고배당기업 분리과세 유지 점검 시스템** — KB-Bridge 종합프로젝트 1조.
A은행 자산관리 고객이 가진 고배당주가 내년에도 분리과세 대상으로 남을지, 신청하면 세금이 얼마나 달라지는지 근거와 함께 미리 점검하는 웹 서비스입니다(내 배당 점검은 챗봇 add-on). 고배당기업 638사의 공시·재무·주가를 분석한 데이터 이야기 11장도 함께 보여 줍니다.

## 폴더 구조

맨 위에는 README.md·requirements.txt·CLAUDE.md만 두고 나머지는 모두 폴더 안에 있습니다. 저장소의 모든 파일과 한 줄 설명입니다. `data/raw/`·`data/db/`는 크기와 비밀 때문에 Git에 올리지 않아 자리만 보입니다.

```
FINAL_PROJECT_ONE_PICK/
├─ README.md                                            # 이 문서: 프로젝트 소개, 모든 파일 구조와 설명, 설치·실행 방법
├─ requirements.txt                                     # pip로 설치할 파이썬 패키지와 정확한 버전 (맨 끝 -e ./source 는 source/ 코드 설치)
├─ CLAUDE.md                                            # AI 작업 도우미(Claude Code)에게 주는 이 프로젝트의 작업 규칙
├─ .gitignore                                           # Git에 올리지 않을 파일 목록 (비밀값 .env, 큰 원본 data/raw, DB 덤프, node_modules 등)
├─ source/                                              # 계산·분석 코드와 파이썬 설정 (pip install -r requirements.txt 하면 python -m scripts.이름으로 실행)
│  ├─ api/                                              # FastAPI 서버 (웹이 부르는 창구, 고객 입력은 저장 안 함)
│  │  ├─ __init__.py                                    # api 패키지 표시 (내용 없음)
│  │  ├─ data.py                                        # API가 돌려줄 값 만들기. 계산은 source/core/ 모듈을 그대로 부르고, 여기서는 JSON 모양만 맞춘다
│  │  └─ main.py                                        # 원픽 API: 새 화면(app/web/)이 쓰는 JSON
│  ├─ core/                                             # 판정·최소 필요 배당·세액·분석 엔진과 DB 연결
│  │  ├─ sources/                                       # 외부 자료 받기 (OpenDART·KRX·법령·KIND)
│  │  │  ├─ __init__.py                                 # 외부 자료 수집과 결측 보완
│  │  │  ├─ base.py                                     # 수집 공통 부품: 결측 상태, 숫자 변환, 재시도·원본 캐시, 출처 기록, 이어받기
│  │  │  ├─ kind.py                                     # KIND 고배당기업 목록(엑셀 내려받기) 읽기와 결측 점검
│  │  │  ├─ krx.py                                      # KRX 수정주가·시장지수(pykrx) 수집과 결측 구분
│  │  │  ├─ law.py                                      # 국가법령정보센터 Open API 법령 원문 수집과 결측 보완
│  │  │  ├─ opendart.py                                 # OpenDART 수집과 결측 보완
│  │  │  └─ samples.py                                  # 인터넷·키 없이 결측 보완 흐름을 보여 주는 가짜 응답. 테스트와 팀 공유 노트북이 함께 쓴다
│  │  ├─ __init__.py                                    # core 패키지 표시 (내용 없음)
│  │  ├─ analysis_data.py                               # S-01 데이터 분석 화면이 읽는 이벤트 스터디 결과 (onepick DB: core.core_event_summary, core.core_event_curve)
│  │  ├─ b_income.py                                    # 배당소득 B와 판정에 쓰는 2024·2025 배당액을 정한다. DB 없이 시험할 수 있게 순수 함수로 둔다
│  │  ├─ behavior_data.py                               # 회사 행동 분석(금리·환율 노출도, 분리과세 이중차분) 결과 저장·읽기 (core.core_behavior_fit, core.core_behavior_series)
│  │  ├─ bunching.py                                    # 기준선 쏠림 계산: 배당성향이 25%·40% 기준선 바로 위에 유난히 몰렸는지 센다
│  │  ├─ capacity.py                                    # F-06 재무 여력: 최소 필요 배당액이 회사에 얼마나 부담인지 보는 지표. 합격점은 두지 않는다 (PRD v0.2 F-06)
│  │  ├─ capacity_map.py                                # 배당 여력 지도 (분석 설계 B2): '2027년에 얼마나 더 내야 하나' × '그만큼 낼 현금이 있나'로 네 칸에 나눈다
│  │  ├─ chat_guard.py                                  # 고정 안내 문구: 세법 해석·절세 방법·종목 추천·주가 질문에는 AI가 답을 만들지 않는다
│  │  ├─ chat_parse.py                                  # 챗봇 입력 해석: 고객이 친 문장에서 값을 뽑고 검사한다
│  │  ├─ checkup.py                                     # 챗봇 점검: 고객의 보유 종목·소득 답변을 받아 판정·최소액·밸류업·세액 엔진을 한 번에 돌린다
│  │  ├─ company_alias.py                               # 자주 틀리거나 다르게 부르는 회사 이름 표 (data/processed/chat/company_alias.csv): 줄임말·영문·옛 이름·오타·자회사 → 대상 기업
│  │  ├─ company_repo.py                                # DB의 실제 회사 638곳을 챗봇 점검(core.checkup)이 쓰는 회사 모양으로 읽는다
│  │  ├─ core_tables.py                                 # raw·02·07 → core 테이블 행, 그리고 판정·최소액 결과 행. DB 없이 시험할 수 있게 순수 함수로 둔다
│  │  ├─ dart_capital.py                                # 증자·감자(OpenDART 주요사항보고서 API)와 액면분할·병합(DART 원문 표) 수집·해석
│  │  ├─ dart_doc.py                                    # DART 공시 원문 읽기: 받기(캐시) → 목차 → 표를 줄로 → 재무제표 한 장 읽기 → 검산
│  │  ├─ dart_fill.py                                   # DB 빈칸을 DART 원문에서 다시 읽어 채울 값을 만든다. 원본 표는 고치지 않고 core.core_dart_fill에 따로 둔다
│  │  ├─ dart_verify.py                                 # DB의 재무제표 값을 그 연도 자기 사업보고서(DART 원문)와 한 칸씩 대조한다. 원본 표는 고치지 않는다
│  │  ├─ dart_xml.py                                    # OpenDART 원문 XML(사업보고서 zip 안의 본문) 표 읽기
│  │  ├─ db.py                                          # PostgreSQL 연결과 적재 도우미 (PRD v0.2 테이블, source/db/schema.sql)
│  │  ├─ event_stats.py                                 # 이벤트 스터디 통계 방법 모음 (numpy만 사용). 여러 방법의 결론이 같은지 보려고 둔다
│  │  ├─ event_study.py                                 # 과거 사례 리포트(데이터 분석 화면): 공시 뒤 주가 반응 이벤트 스터디
│  │  ├─ exposure_dividend.py                           # 금리·환율 노출도와 배당 결정 (회사×연도 패널, 노출도 차이 분석)
│  │  ├─ faq_search.py                                  # 금융 상식 찾기: 고객 질문과 가까운 고정 답변 하나를 그대로 돌려준다 (검색만, 생성 없음)
│  │  ├─ group_compare.py                               # 두 무리 비교와 예측 모델(로지스틱 회귀) 계산 (분석 설계 A2·A3)
│  │  ├─ holder_analysis.py                             # 추가 분석 '최대주주 지분 비교': 2025 기준선 근처 회사와 나머지의 최대주주+특수관계인 보통주 지분율 분포. 회사·개인 이름 없이 집계만
│  │  ├─ isa_irp.py                                     # ISA·IRP 구간 안내와 단순 계산 (발표 자료 ISA·IRP 1~3, 부록 A~C)
│  │  ├─ judgement.py                                   # 1층 요건 판정: 고배당기업 요건(조세특례제한법 제104조의27 제1항) 충족 여부
│  │  ├─ keyboard.py                                    # 한/영 전환을 잊고 친 글('tkatjdwjswk 10wn' → '삼성전자 10주')을 두벌식 자판 기준으로 한글로 되돌린다
│  │  ├─ law_search.py                                  # 관련 조문 찾기: 고객 질문과 가까운 조문 문단을 원문 그대로 돌려준다 (검색만, 생성 없음)
│  │  ├─ llm_ollama.py                                  # 서버 안의 Ollama로 챗봇 입력 문장에서 값만 뽑는다 (core.chat_parse.Parser의 llm 자리)
│  │  ├─ macro.py                                       # 한국은행 ECOS 거시지표(경상수지·금리·환율·GDP·CPI·고용)를 받아 원문 그대로 표로 바꾼다
│  │  ├─ macro_dividend.py                              # 배당과 거시지표의 상관 (사업연도 단위)
│  │  ├─ major_holder.py                                # 최대주주 현황(OpenDART hyslrSttus): 응답 → raw.dart_major_holder 행, 회사별 보통주 지분율 합계·최대주주 종류
│  │  ├─ min_dividend.py                                # 최소 필요 배당액: 2027 사업연도 배당도 고배당기업 요건을 채우려면
│  │  ├─ p1_analysis.py                                 # F-08 데이터 분석 화면 P1: 소급 분석·최소액 분포·기준선 몰림. 회사 이름·순위 없이 집계만 돌려준다
│  │  ├─ payout_change.py                               # 2025 배당성향이 25%를 넘은 이유를 회사별로 나눈다 (분석 설계 A1)
│  │  ├─ personas.py                                    # 원픽 핵심 페르소나 2인 (팀 문서 '원픽 페르소나.docx', 2026-11-02). 로그인한 A은행 고객으로 가정한 시연용 가상 인물
│  │  ├─ policy_did.py                                  # 고배당기업 배당소득 분리과세가 배당 결정을 바꿨나 (이중차분·사건연구)
│  │  ├─ policy_docs.py                                 # 배당·주주환원 정책 문서(기업가치 제고 계획·기업지배구조보고서·주주환원 공정공시)를 문서째 받아 글자와 문단으로 나눈다
│  │  ├─ policy_extract.py                              # F-03·F-07: 기업가치 제고 계획 공시 본문에서 배당 목표·배당 정책 문장을 뽑는다 (사람이 원문 확인하기 전 후보)
│  │  ├─ policy_filings.py                              # 4층 배당 정책 상세(P1): 자사주 매입·소각, 투자·인수 공시 → raw.dart_policy_filing 행
│  │  ├─ policy_promise.py                              # 밸류업 계획 문단에서 약속(숫자 목표·실행 약속)을 정해진 단어 규칙으로 찾는다 (분석 설계 D1)
│  │  ├─ price_groups.py                                # 무리별 주가 누적 수익률 (분석 설계 C2)
│  │  ├─ price_quality.py                               # KRX 주가·지수의 날짜별 사용 등급 (사용 가능 / 주의 / 제외). 원본 행은 지우지 않고 표시만 만든다
│  │  ├─ raw_tables.py                                  # 원천 엑셀(01~09) → raw 테이블 행. DB 없이 시험할 수 있게 DataFrame을 받아 dict 목록을 돌려준다
│  │  ├─ retention.py                                   # 고배당기업 요건을 다음 해에도 유지할까 — 과거 유지·탈락 표와 탈락 예측 (분석 설계 B1)
│  │  ├─ sample_data.py                                 # 화면 문구와 데이터 분석 화면의 자리값
│  │  ├─ share_check.py                                 # 주식 총수(raw.dart_share_total) 이상치 판정 → core.core_share_check. 원본은 고치지 않고 사유와 보정 배수만 남긴다
│  │  ├─ share_total.py                                 # 주식의 총수 현황(OpenDART stockTotqySttus): 발행주식총수·자기주식수·유통주식수 → raw.dart_share_total 행
│  │  ├─ source_verify.py                               # 원천 자료(회사 목록·배당 표 전체 항목·배당 결정 공시·KIND 고배당 공시)를 DART 원문에서 다시 읽어 칸마다 대조한다
│  │  ├─ tax.py                                         # 2층 세액 비교: 2026년에 받는 배당(2027년 5월 신고분)의 분리과세 신청 전후 소득세
│  │  ├─ tax_rates.py                                   # 세율표(PRD tax_rate 테이블과 같은 구조). 한 행 = 세율 구간 1개(시행 기간·출처 포함)
│  │  ├─ term_dict.py                                   # 금융 용어 사전 찾기: 금융위원회 금융용어사전 + 원픽 보충 용어 (챗봇 용어 질문)
│  │  ├─ usage.py                                       # 이용 통계: 입력값 없이 점검 시작·완료·상담 연결 횟수만 센다
│  │  ├─ valueup.py                                     # 밸류업 약속 비교: 회사의 배당 목표를 2026 사업연도 배당총액으로 환산해 최소 필요 배당액과 비교한다
│  │  └─ virtual_cases.py                               # 시연용 가상 회사·가상 고객. 실제 회사·개인 정보가 아니며 모든 화면에 '가상 사례'를 표시한다
│  ├─ db/                                               # PostgreSQL 표 설계 SQL
│  │  ├─ schema.sql                                     # onepick DB의 모든 표 만들기 SQL (raw 원본 · core 분석 · ref 기준표)
│  │  └─ schema_capital.sql                             # 증자·감자·액면분할·병합 공시 표 만들기 SQL
│  ├─ notebooks/                                        # 코랩 데이터 수집 노트북
│  │  ├─ 01_기업_매핑표_만들기.ipynb                    # 01. 기업 매핑표 만들기 (KIND · OpenDART · 시장구분)
│  │  ├─ 02_연결재무제표_수집.ipynb                     # 02. 연결재무제표 수집 (연결감사보고서 기준)
│  │  ├─ 03_별도재무제표_수집.ipynb                     # 03. 별도재무제표 수집 (감사보고서 기준)
│  │  ├─ 04_KRX_시세_수집.ipynb                         # 04. KRX 수정주가 · 시장지수 수집 (pykrx)
│  │  └─ 05_법령_원문_수집.ipynb                        # 05. 법령 원문 수집 (국가법령정보센터)
│  ├─ scripts/                                          # 수집·적재·분석·보고서 실행 스크립트
│  │  ├─ ofs_review/                                    # 별도재무제표 원문 대조 도구
│  │  │  ├─ README.md                                   # 별도재무제표 보완 자료(03) 원문 대조
│  │  │  ├─ __init__.py                                 # ofs_review 패키지 표시 (내용 없음)
│  │  │  ├─ dartdoc.py                                  # DART 공시 원문 읽기 도우미: 접수번호 → 목차(섹션) → 섹션 글자. 받은 HTML은 cache/에 저장해 다시 받지 않는다
│  │  │  ├─ export_result_csv.py                        # 원문 대조 결과(final_verdict.csv·verify_ni.csv) → report/검증/별도재무제표_원문대조_결과.csv (팀 공유용 칸별 결과)
│  │  │  ├─ final_verdict.py                            # 1차(원문 URL 문서)·2차(자기 연도 사업보고서) 확인을 합쳐 칸마다 최종 판정. 결과: dart/final_verdict.csv
│  │  │  ├─ make_request_md.py                          # 03 별도재무제표 보완 자료 → 확인 요청 문서(md). 모든 숫자는 이 스크립트가 원본 CSV에서 센다
│  │  │  ├─ verify_mismatch.py                          # API·원문 불일치 칸을 DART 원문으로 다시 확인한다
│  │  │  ├─ verify_ni.py                                # Q8: 감사보고서 당기순이익_전체와 배당 표 당기순이익이 1% 넘게 다른 칸을 그 연도 사업보고서 별도 손익계산서로 확인. 결과: dart/verify_ni.csv
│  │  │  └─ verify_own_year.py                          # 1차 판정에서 결론이 안 난 칸을 '그 연도 자기 사업보고서'의 별도 재무제표로 다시 확인한다
│  │  ├─ prd/                                           # PRD 양식(docx) 칸 채우기 도구
│  │  │  ├─ README.md                                   # PRD docx 수정 도우미
│  │  │  ├─ __init__.py                                 # prd 패키지 표시 (내용 없음)
│  │  │  ├─ edit_prd.py                                 # PRD v0.1 → v0.2 수정사항(2026-10-22)을 document.xml에 반영한다
│  │  │  └─ paras.py                                    # PRD 원본 양식(docx)의 document.xml에서 찾는 낱말이 든 문단 번호와 글을 찍는다 (양식 칸 번호 찾기용)
│  │  ├─ __init__.py                                    # scripts 패키지 표시 (내용 없음)
│  │  ├─ analysis_bunching.py                           # 25% 기준선 쏠림 분석 결과를 report/분석/기준선_몰림_분석_결과.md로 쓴다 (분석 설계 2절, source/core/bunching.py)
│  │  ├─ analysis_capacity_map.py                       # 배당 여력 지도(B2)를 report/분석/배당_여력_지도_결과.md와 output/charts/배당_여력_지도*.svg로 쓴다
│  │  ├─ analysis_event_valueup.py                      # 밸류업 계획 첫 공시·고배당기업 공시 뒤 주가 반응(C1)을 report/분석/밸류업_고배당공시_주가반응_결과.md로 쓴다
│  │  ├─ analysis_groups.py                             # 공시 시기별 비교(A2)와 최대주주 유형과 기준선 쏠림의 관계(A3)를 report/분석/공시시기_최대주주_비교_결과.md로 쓴다
│  │  ├─ analysis_industry_value.py                     # 업종 안 수익성·안정성 위치(B3)와 배당수익률·PBR 비교(C3)를 report/분석/업종_위치_주가수준_결과.md로 쓴다
│  │  ├─ analysis_payout_change.py                      # 2025 배당성향이 25%를 넘은 이유(배당 증가 vs 순이익 감소)를 report/분석/배당성향_변화_분해_결과.md로 쓴다 (분석 설계 A1)
│  │  ├─ analysis_policy_promise.py                     # 밸류업 계획 약속 분류(D1): 638사 문단에서 약속 후보를 찾아 report/분석/밸류업_약속_분류_결과.md와 검토표를 만든다
│  │  ├─ analysis_price_groups.py                       # 무리끼리 주가 비교(C2)를 report/분석/무리별_주가_비교_결과.md로 쓴다
│  │  ├─ analysis_promise_actual.py                     # 밸류업 약속과 실제(D2)를 report/분석/밸류업_약속_실제_결과.md로 쓴다
│  │  ├─ analysis_retention.py                          # 고배당기업 유지 가능성(B1)을 report/분석/유지가능성_분석_결과.md로 쓴다
│  │  ├─ analyze_exposure_dividend.py                   # 금리·환율 노출도와 배당 결정을 계산해 report/분석/배당_노출도_분석_결과.md와 CSV로 남긴다 (source/core/exposure_dividend.py)
│  │  ├─ analyze_macro_dividend.py                      # 배당과 거시지표의 상관을 계산해 report/분석/배당_거시지표_상관_결과.md와 CSV로 남긴다 (source/core/macro_dividend.py)
│  │  ├─ analyze_panel.py                               # 우리 638사(배당 기업)와 4조 대조군 비교 분석 → 마크다운 보고서 (partner.v_panel)
│  │  ├─ analyze_policy_did.py                          # 고배당기업 배당소득 분리과세의 배당 결정 효과(이중차분)를 계산해 report/분석/배당_제도효과_분석_결과.md와 CSV로 남긴다
│  │  ├─ analyze_profit_dividend.py                     # 회사 이익 변화와 주당배당금 변화가 같이 움직였는지 → data/processed/analysis/profit_dividend.json
│  │  ├─ build_capacity.py                              # F-06 재무 여력 표 core.core_capacity_2025를 만든다 (source/scripts/build_judgement.py 다음에 실행)
│  │  ├─ build_core.py                                  # raw 스키마 + 02·07 가공본 → core 스키마, 그리고 판정·최소액 계산
│  │  ├─ build_events.py                                # 배당 결정·KIND 고배당·증자·감자·분할·병합 공시 → 이벤트 스터디(CAR) → core.core_event_car, core_event_summary, core_event_curve
│  │  ├─ build_judgement.py                             # B(2024·2025)를 채우고 2026 판정·2027 최소 필요 배당액을 다시 계산한다 (source/scripts/build_core.py 다음에 실행)
│  │  ├─ build_share_check.py                           # 주식 총수 이상치 표 core.core_share_check를 만든다 (source/scripts/collect_share_total.py 다음에 실행)
│  │  ├─ capital_dividend_change.py                     # 증자·감자·분할·병합 공시마다 그 회사의 배당이 전년보다 늘었는지 → 엑셀 (output/tables/증자감자_배당증감_YYYYMMDD.xlsx)
│  │  ├─ check_did_pretrend.py                          # 이중차분(9장 '개인 최대주주 회사 × 2025년')의 평행추세 가정을 숫자로 점검한다. 결과 파일은 만들지 않고 화면에만 찍는다
│  │  ├─ check_ocr_quality.py                           # OCR 정확도 점검: 글자층이 있는 PDF 쪽을 일부러 OCR해 글자층(정답)과 비교한다
│  │  ├─ check_review_workbook.py                       # 전수 검산표 엑셀의 '수식' 칸을 파이썬으로 똑같이 계산해 결과별 행 수를 센다 (LibreOffice 없이 수식 결과 확인용)
│  │  ├─ check_rules_independent.py                     # 판정·세액을 엔진과 따로 조문대로 다시 계산해 DB·엔진과 대조 (report/검증/최종_점검_결과_20261104.md)
│  │  ├─ collect_fsc_glossary.py                        # 금융위원회 금융용어사전(누리집 '금융용어설명')을 data/processed/term/fsc_glossary.json으로 받는다
│  │  ├─ collect_macro.py                               # 데이터셋 기간(배당 2017~·주가 2018~)에 맞춰 2016~2026 거시지표를 한국은행 ECOS에서 받아 CSV로 저장한다
│  │  ├─ collect_major_holder.py                        # 638사 최대주주 현황을 OpenDART에서 받아 raw.dart_major_holder에 넣고, core.core_major_holder(지분율 합계·개인/법인)를 만든다
│  │  ├─ collect_partner_prices.py                      # 4조 대조군 상장사 수정 종가 → partner.krx_price_daily (네이버 금융 차트 공개 자료)
│  │  ├─ collect_policy_docs.py                         # 배당·주주환원 정책 문서를 DART에서 문서째 받아 DB에 넣는다 → raw.policy_filing / policy_document / policy_chunk
│  │  ├─ collect_policy_filings.py                      # 시연 10개사의 자사주 매입·소각, 투자·인수 공시를 OpenDART에서 받아 raw.dart_policy_filing에 넣는다 (4층 배당 정책 상세)
│  │  ├─ collect_pref_dividend_class.py                 # 배당 결정 공시의 '종류주식에 대한 배당 관련 사항' 표 → raw.dividend_decision_class (우선주 종목별 1주당 배당금)
│  │  ├─ collect_pref_stocks.py                         # 고배당기업 638곳의 상장 우선주 종목 → raw.krx_pref_stock, 그리고 core.core_company의 우선주 칸을 고친다
│  │  ├─ collect_share_total.py                         # 638사 주식의 총수 현황(발행·자기·유통)을 OpenDART에서 받아 raw.dart_share_total에 넣는다
│  │  ├─ eval_chat_ai.py                                # 챗봇 보유 종목 해석 정답률 점검: 실제 Ollama와 회사 목록으로 시험 문장을 해석해 정답과 비교한다
│  │  ├─ event_methods.py                               # 이벤트 스터디를 여러 통계 방법으로 다시 계산해 결론이 같은지 본다 → report/분석/이벤트스터디_방법별_결과.md
│  │  ├─ event_significance.py                          # 이벤트 스터디 결과가 우연인지 본다 (core.core_event_car, 2025년까지 공시). scipy 없이 표준 라이브러리·numpy로 계산
│  │  ├─ export_b2024.py                                # 2024 사업연도 배당소득 B(2024) 자료 → 엑셀 한 장 (KIND 고배당기업 공시 원문 값 + DART 현금배당총액 D 비교)
│  │  ├─ export_capital_check.py                        # onepick DB 증자·감자·분할·병합 표 → 팀 검산용 엑셀 (source/scripts/load_capital.py로 적재한 뒤)
│  │  ├─ export_dataset.py                              # 분석에 쓰는 데이터 전체를 엑셀 한 파일로 → output/tables/원픽_분석데이터_<날짜>.xlsx
│  │  ├─ export_db.py                                   # onepick DB 전체를 다른 사람에게 넘길 파일로 뽑는다 → data/db/onepick_YYYYMMDD.dump + .json
│  │  ├─ export_duckdb.py                               # onepick DB를 DuckDB 파일 하나로 내보낸다(제출·공유용이자 PostgreSQL 복구 파일: 표·보기 값, 원래 자료형, 스키마 SQL, 표마다 행 수·확인값)
│  │  ├─ export_mismatch_review.py                      # 원문 대조 불일치 칸 → 사람 검토용 표 report/검증/DART_불일치_검토표.csv (엑셀에서 열기 좋게 UTF-8 BOM)
│  │  ├─ export_ocr_review.py                           # OCR 사람 검토표 (output/tables/OCR_검토표_YYYYMMDD.xlsx). 쪽 그림과 OCR 글자를 나란히 보고 확인·정정한다
│  │  ├─ export_partner_workbook.py                     # 4조참치 협조 데이터 전부 → 우리 전수 검산표 형식 엑셀 (대조군 또는 겹치는 회사)
│  │  ├─ export_policy_review.py                        # 시연 10개사 기업가치 제고 계획 공시 → 배당 목표·정책 문장 검토표 (F-03·F-07, 사람이 원문 확인)
│  │  ├─ export_review_workbook.py                      # onepick DB 전체 → 파트별 전수 검산표 엑셀 (사람이 원문과 한 행씩 맞춰 보는 용도)
│  │  ├─ export_share_check.py                          # 주식 총수(발행·자기·유통) 검산표 → 엑셀 (API 값·보정값·이상치 사유, 자본금·PBR·배당 교차 대조, 원문 대조)
│  │  ├─ fill_from_dart.py                              # DB 빈칸을 DART 원문으로 다시 확인해 core.core_dart_fill에 적는다. 원본 표는 고치지 않는다
│  │  ├─ html_to_pdf.swift                              # HTML 파일을 A4 PDF로 바꾸는 macOS 도구 (보고서 PDF용)
│  │  ├─ link_policy_corrections.py                     # 정책 공시마다 최초 접수번호(root_rcept_no)를 채워 정정 공시를 원래 공시와 잇는다
│  │  ├─ load_capital.py                                # 증자·감자·액면분할·병합 공시 → onepick DB (source/db/schema_capital.sql)
│  │  ├─ load_macro.py                                  # ECOS 거시지표 CSV(data/raw/macro/) → onepick DB raw.ecos_macro
│  │  ├─ load_ocr_review.py                             # 검토를 마친 OCR 검토표 → raw.policy_page_ocr 검토 칸, 정정 글자는 검색 문단(raw.policy_chunk)에도 반영
│  │  ├─ load_partner.py                                # 4조참치 협조 자료 → onepick DB partner 스키마 (source/db/schema.sql partner.*)
│  │  ├─ load_policy_review.py                          # 검토를 마친 밸류업 정책 검토표 → core.core_policy_item ('확인완료' 행만)
│  │  ├─ load_prices.py                                 # KRX 수정 종가·시장지수·빈칸 사유 → onepick DB, 그리고 날짜별 사용 등급(source/core/price_quality.py)
│  │  ├─ load_raw.py                                    # 원천 엑셀(01·04·04-1·04-2·05·09) → onepick DB의 raw 스키마, 세율표 → ref.tax_rate
│  │  ├─ load_review_workbook.py                        # 검토를 마친 전수 검산표·증자감자 검산표 → DB (팀이 원문을 보고 확정한 값)
│  │  ├─ ocr_ai_review.py                               # OCR 검토 대상 쪽을 Claude(AI)가 쪽 그림과 대조해 검토하는 절차 (사람 검토 전 단계)
│  │  ├─ ocr_ai_review_prompt.md                        # OCR 결과를 AI가 쪽 그림과 대조할 때 주는 지시문 (ocr_ai_review.py가 씀)
│  │  ├─ ocr_policy_docs.py                             # PDF 쪽을 전부 OCR로 읽어 쪽별 결과(raw.policy_page_ocr)와 검색 조각(raw.policy_chunk)에 넣는다
│  │  ├─ pdf_ocr.swift                                  # 그림으로 된 PDF 쪽의 글자를 읽는 macOS OCR 도구 (밸류업 공시 문서용)
│  │  ├─ pdf_text.swift                                 # PDF에서 쪽별 글자를 뽑는 macOS 도구
│  │  ├─ report_dart_fill.py                            # core.core_dart_fill → report/검증/DART_빈칸_채우기_결과.md (사람이 볼 표). 숫자는 모두 DB에서 센다
│  │  ├─ report_dart_verify.py                          # core.core_dart_verify → report/검증/DART_원문대조_재무제표_결과.md. 숫자는 모두 DB에서 센다
│  │  ├─ report_erd_pdf.py                              # onepick DB 전체 ERD PDF → report/설계/DB_ERD_전체.pdf
│  │  ├─ report_event_pdf.py                            # 이벤트 스터디 유의성 보고서 PDF (색 구분) → report/분석/이벤트스터디_유의성_보고서.pdf
│  │  ├─ report_judgement_hold.py                       # 판정 보류인 회사와 사유를 report/분석/판정_보류_정리.md로 쓴다
│  │  ├─ report_story_pdf.py                            # 데이터 이야기 분석 보고서 PDF → report/분석결과_요약보고서.pdf
│  │  ├─ restore_db.py                                  # 넘겨받은 덤프 파일로 onepick DB를 되살리고, 뽑을 때의 확인표(.json)와 행 수를 대조한다
│  │  ├─ restore_duckdb.py                              # export_duckdb로 만든 .duckdb 하나로 PostgreSQL onepick DB를 되살리고, 표마다 행 수·확인값을 대조한다
│  │  ├─ run_api.py                                     # 원픽 API 서버 실행. 접속 기록(access log)은 끈다: 고객 입력을 남기지 않기 위해서다
│  │  ├─ select_demo10.py                               # 시연 10개사를 고른다 → core.core_demo_company (source/scripts/build_capacity.py 다음에 실행)
│  │  ├─ serve_public.py                                # 시연판 API를 이 Mac에서 켜고 Tailscale Funnel로 인터넷에 연다 (웹 화면은 Vercel, report/실행안내/배포_안내.md)
│  │  ├─ story_checks.py                                # 데이터 이야기 보고서의 '확인하는 법': 독자가 그대로 돌려 볼 SQL·명령과, 화면 숫자와 같은지 맞춰 보는 규칙
│  │  ├─ stream_book.py                                 # 전수 검산표 형식(source/scripts/export_review_workbook.py)을 스트리밍(write-only) 엑셀로 쓰기
│  │  ├─ verify_db.py                                   # DB 재무제표 값을 DART 사업보고서 원문과 전수 대조 → core.core_dart_verify
│  │  ├─ verify_resolution.py                           # 코드가 원문과 대조해 '불일치·못 찾음'이 나온 칸이 그 뒤 어떻게 처리됐는지 센다 → data/processed/analysis/verify_resolution.json
│  │  └─ verify_sources.py                              # 원천 표를 DART 원문에서 다시 읽어 칸마다 대조 → core.core_source_verify. 원본 표는 고치지 않는다
│  ├─ tests/                                            # 자동 테스트 (python -m pytest -q)
│  │  ├─ __init__.py                                    # tests 패키지 표시 (내용 없음)
│  │  ├─ conftest.py                                    # 모든 테스트에 공통 설정: 실제 Ollama를 끄고, 이용 통계 숫자를 0에서 시작한다
│  │  ├─ test_api.py                                    # 새 화면용 API (source/api/main.py). 가상 회사(C사·E사)로 돌리고, DB가 있어야 하는 것은 DB가 없으면 건너뛴다
│  │  ├─ test_b_income.py                               # B(배당소득) 규칙: KIND 공시 값 우선, 감액배당 메모가 있으면 B(2025)는 비우고 보류
│  │  ├─ test_bunching.py                               # 기준선 몰림(2장) 계산 테스트: 구간 세기, 예상 곡선, 몰린 회사 수
│  │  ├─ test_capacity.py                               # F-06 재무 여력 규칙: 금융업 미적용, 최소액 없으면 미표시, 잉여현금 ÷ 최소액
│  │  ├─ test_capacity_map.py                           # 배당 여력 지도(5장 현금 여력) 계산 테스트: 네 칸 나누는 경계값
│  │  ├─ test_chat_guard.py                             # 챗봇 고정 안내 테스트: 세법 해석·종목 추천 질문에는 정해 둔 문구로만 답하는지
│  │  ├─ test_chat_parse.py                             # 챗봇 입력 해석 테스트: 금액·종목·주식 수를 규칙으로 읽는지 (한글 숫자, '거의·얼추' 같은 말 포함)
│  │  ├─ test_checkup.py                                # 가상 고객 5건으로 챗봇 점검 전체 흐름 검산 (기획안 10/29~11/01 '고정 가상 고객 5건')
│  │  ├─ test_company_alias.py                          # 자주 틀리는 회사 이름 표(data/processed/chat/company_alias.csv): 바꾼 글로 되묻기만 하고 바로 계산하지 않는다
│  │  ├─ test_components.py                             # API가 쓰는 화면 조각(source/ui/components.py) 테스트: 꼬리표·표·금액 표시
│  │  ├─ test_dart_capital.py                           # 증자·감자 API 응답 해석, 분할·병합 원문 읽기·검산, 키 처리. 네트워크 없이 시험한다
│  │  ├─ test_dart_fill.py                              # DART 원문 읽기·검산과 빈칸 채우기 규칙. 원문 받기는 가짜로 바꿔 네트워크 없이 시험한다
│  │  ├─ test_dart_verify.py                            # DB 값 ↔ DART 원문 대조 규칙: 단위 반올림, 기간 고르기, 불일치 설명. 원문 읽기는 가짜로 바꾼다
│  │  ├─ test_dart_xml.py                               # 사업보고서 원문 XML 정형 표 읽기 (source/core/dart_xml.py)
│  │  ├─ test_db_tables.py                              # PRD v0.2 테이블: 원천 → raw·core 변환(DB 없이)과, 작은 시험 데이터로 스키마·키 확인(DB 있을 때만)
│  │  ├─ test_event_stats.py                            # 이벤트 스터디 통계 방법: 알려진 값으로 확인
│  │  ├─ test_event_study.py                            # 이벤트 스터디(6장) 테스트: 공시일 맞추기, 누적 초과수익률, 겹치는 공시 빼기, 요약 통계
│  │  ├─ test_exposure_dividend.py                      # 금리·환율 노출도와 배당(8장 보조) 계산 테스트: 차입금·외화 계정 합치기
│  │  ├─ test_faq_search.py                             # 금융 상식 찾기: 미리 써 둔 답만 돌려주고, 상관없는 말에는 답하지 않는다
│  │  ├─ test_group_compare.py                          # 두 집단 비교 테스트: 가운데 값 차이, 결측 빼기, 부트스트랩 범위
│  │  ├─ test_isa_irp.py                                # ISA·IRP 계산이 발표 자료(ISA·IRP 2 · 계산 예시)의 숫자와 같은지
│  │  ├─ test_judgement.py                              # 요건 판정 경계값: 25%·40%·10%의 바로 아래와 경계, 순이익 0원, 부채 정확히 2배, 자본잠식, 전전 무배당
│  │  ├─ test_keyboard.py                               # 한/영 전환을 잊고 친 글을 한글로 되돌리기 (core.keyboard)
│  │  ├─ test_law_search.py                             # 관련 조문 찾기: 실제 Ollama 없이 가짜 임베딩과 저장된 원문으로 확인한다
│  │  ├─ test_llm_ollama.py                             # Ollama 연결: 실제 Ollama 없이 가짜 응답으로 확인한다 (꺼짐·시간 초과·깨진 JSON·이상한 값)
│  │  ├─ test_load_partner.py                           # 4조참치 자료 → partner 스키마 (source/scripts/load_partner.py). 단위 풀이는 DB 없이, 적재는 시험 DB가 있을 때만
│  │  ├─ test_load_review_workbook.py                   # 검토본 반영: 정정 메모의 원문 값, 오타 칸, 원문 대조 우선순위
│  │  ├─ test_macro.py                                  # 한국은행 ECOS 거시지표 받기 테스트: 여러 쪽 이어 받기, 값 정리
│  │  ├─ test_macro_dividend.py                         # 경기와 배당(8장) 계산 테스트: 연간 합·평균, 덜 찬 해 빼기, 순열 검정
│  │  ├─ test_major_holder.py                           # 최대주주 현황(OpenDART hyslrSttus): 응답 → 행, 지분율 합계·개인/법인 규칙, 기준선 근처 비교. 실제 API는 부르지 않는다
│  │  ├─ test_min_dividend.py                           # 최소 필요 배당액: 최소액이면 통과, 1원 모자라면 미충족
│  │  ├─ test_ocr.py                                    # PDF 전 쪽 OCR: 출력 읽기, 다시 읽은 결과 고르기, 검토 대상 가르기, 검토표 왕복
│  │  ├─ test_p1_analysis.py                            # F-08 소급 분석·최소액 분포·기준선 몰림 집계 규칙
│  │  ├─ test_partner_prices.py                         # 4조 대조군 주가 받기 (source/scripts/collect_partner_prices.py): 응답 읽기
│  │  ├─ test_partner_workbook.py                       # 4조참치 대조군 검산표: 값 읽기와 '원문에 없음' / '실재하지만 불러올 수 없음' 구분
│  │  ├─ test_payout_change.py                          # 배당성향 변화 분해 테스트: 이미 기준을 넘은 회사, 이익·배당 몫 나누기
│  │  ├─ test_policy.py                                 # F-03·F-07: 정책 문장 뽑기, 검토표 왕복, 확인완료만 목표로
│  │  ├─ test_policy_did.py                             # 세금 제도와 배당(9장 이중차분) 테스트: 필요한 증가율, 처리군·비교군 나누기
│  │  ├─ test_policy_filings.py                         # 4층 배당 정책 상세: 자사주·투자·인수 공시 응답 → 행, 뷰의 숫자·날짜 읽기, 카드 ⑥ '관련 공시' 표시
│  │  ├─ test_policy_promise.py                         # 밸류업 약속 읽기 테스트: 배당성향 목표 같은 약속 문장을 숫자로 바꾸기
│  │  ├─ test_pref_stocks.py                            # 우선주: 상장 우선주 찾기(source/scripts/collect_pref_stocks.py), 우선주 회사 자료, 챗봇 인식·계산
│  │  ├─ test_price_groups.py                           # 무리별 주가 비교 테스트: 시작일·확인일 고르기와 누적 수익률
│  │  ├─ test_price_quality.py                          # KRX 주가·지수 사용 등급: 상한 초과 등락, 같은 가격 연속 구간의 경계값
│  │  ├─ test_report_erd_pdf.py                         # DB 전체 ERD: 모든 표·보기가 빠짐없이 들어가고, 연결 비율을 실제로 센다
│  │  ├─ test_report_story_pdf.py                       # 데이터 이야기 보고서: 확인용 SQL이 화면 값과 같고, 요약 장·장 11개와 부록의 모든 조합이 빠짐없이 들어가는지
│  │  ├─ test_restore_db.py                             # DB 덤프 되살리기 테스트: 표 행 수 비교, 가장 새 덤프 고르기
│  │  ├─ test_restore_duckdb.py                         # DuckDB 복구 파일 테스트: 확인값 SQL(numeric·시각 맞춤), JSON 옮기기
│  │  ├─ test_retention.py                              # 다음 해 탈락 예측(4장) 테스트: 특징 7개 만들기, 로지스틱 회귀·AUC
│  │  ├─ test_review_workbook.py                        # 전수 검산표: 주식 종류 구분과 수식 규칙(파이썬 판)
│  │  ├─ test_share_check.py                            # 주식 총수 이상치 판정: 자본금 대조와 PBR로 API 1,000배 오류를 가려내고, 나머지는 사유만 남긴다
│  │  ├─ test_share_total.py                            # 주식의 총수 현황(OpenDART stockTotqySttus): 숫자 읽기, 응답 → 행, 키 찾기. 실제 API는 부르지 않는다
│  │  ├─ test_sources_base.py                           # 수집 공통 부품: 숫자 변환, 단위, 비밀키, 재시도·캐시, 이어받기
│  │  ├─ test_sources_krx_law_kind.py                   # KRX 시세·법령 원문·KIND 목록의 결측 구분(가짜 응답, 인터넷 없이)
│  │  ├─ test_sources_opendart.py                       # OpenDART 결측 보완: 가짜 응답(core.sources.samples)으로 인터넷·키 없이 검사한다
│  │  ├─ test_tax.py                                    # 세액 비교: 세율 구간 경계, 기획안 예시, 가상 고객 5건
│  │  ├─ test_usage.py                                  # 이용 통계(횟수만 세기) 테스트: 정해 둔 사건만 세는지. 시연판 서버에는 아직 연결하지 않음
│  │  └─ test_valueup.py                                # 밸류업 배당 약속과 최소 필요 배당 비교 테스트 (화면에서는 뺀 기능의 계산)
│  ├─ ui/                                               # API가 쓰는 금액 표시 도구
│  │  ├─ __init__.py                                    # ui 패키지 표시 (내용 없음)
│  │  └─ components.py                                  # 여러 화면에서 함께 쓰는 부품. *_html 함수는 HTML 문자열만 만든다
│  ├─ pyproject.toml                                    # 파이썬 프로젝트 설정: 필요한 패키지, 테스트 위치(tests), source/ 패키지 설치 방법
│  └─ uv.lock                                           # uv가 고정한 패키지 버전 잠금 파일 (손으로 고치지 않음)
├─ data/                                                # 데이터 (큰 원본은 Git에 안 올림)
│  ├─ db/                                               # DB 덤프 파일 (Git 제외, 팀원에게 직접 전달)
│  ├─ partner/                                          # 대조군 데이터
│  │  └─ 4조참치_20261030/                              # 대조군 데이터 설명과 겹치는 회사 비교 (원본은 Git 제외)
│  │     ├─ README.md                                   # 대조군 데이터 (2026-10-30 받음)
│  │     └─ 겹침_차이_원인_20261102.csv                 # 대조군 데이터와 우리 638사가 겹치는 회사에서 값이 다른 칸과 그 원인 분류
│  ├─ processed/                                        # 화면·검색이 쓰는 가공 파일
│  │  ├─ analysis/                                      # 화면이 읽는 분석 결과 숫자
│  │  │  ├─ event_methods.json                          # 6장 공시 뒤 주가: 계산 방법별 결과 숫자 (화면이 읽음, source/scripts/event_methods.py가 만듦)
│  │  │  ├─ profit_dividend.json                        # 8장 회사 이익과 배당 변화의 상관 결과 (source/scripts/analyze_profit_dividend.py가 만듦)
│  │  │  └─ verify_resolution.json                      # 11장 데이터 뒷이야기: 원문 대조에서 걸린 칸이 어떻게 처리됐는지 집계 (source/scripts/verify_resolution.py)
│  │  ├─ chat/                                          # 챗봇이 쓰는 표
│  │  │  └─ company_alias.csv                           # 챗봇이 회사 별명·줄임말을 정식 이름으로 바꾸는 표 (예: 삼전 → 삼성전자)
│  │  ├─ faq/                                           # 금융 상식 답
│  │  │  ├─ embeddings.json                             # 금융 상식 답을 고를 때 쓰는 문장 벡터 (bge-m3로 만듦, finance_faq.json과 짝)
│  │  │  └─ finance_faq.json                            # 금융 상식 질문과 미리 써 둔 답 원문 (팀 초안, 출처 표기)
│  │  ├─ law/                                           # 조문 원문
│  │  │  ├─ articles.json                               # 조세특례제한법·소득세법 등 조문 원문 문단 (국가법령정보센터에서 받음)
│  │  │  └─ embeddings.json                             # 관련 조문 찾기에 쓰는 문단 벡터 (bge-m3로 만듦, articles.json과 짝)
│  │  ├─ review/                                        # 원문 대조로 고친 값
│  │  │  ├─ 우선주_종목별_배당금_2025.csv               # 우선주 종목별 2025 배당금 (사업보고서 원문으로 확인, 우선주 계산에 씀)
│  │  │  ├─ 원문대조_20261102.csv                       # 11-02 사업보고서 원문으로 고친 배당·재무 값 (DB 반영용)
│  │  │  └─ 재무_원문대조_20261029.csv                  # 10-29 재무 값 원문 대조로 고친 목록 (팀 검토본 반영용)
│  │  └─ term/                                          # 용어 풀이
│  │     ├─ fsc_glossary.json                           # 금융위원회 금융용어사전에서 받은 용어 풀이 (출처 있음)
│  │     └─ onepick_terms.json                          # 원픽 보충 금융 용어 132개 풀이와 출처 (칼럼 용어 사전·금융 상식 답·금융위원회 사전에 없는 말, 팀 검토 전)
│  └─ raw/                                              # 받은 원본 약 2.1GB (Git 제외)
├─ app/                                                 # 사용자 화면 (Streamlit + React 웹)
│  ├─ verify/                                           # Streamlit과 웹·API 숫자 대조 도구
│  │  ├─ api_same.py                                    # ① 데이터 대조: 웹 화면이 8000 서버에서 받는 JSON과 Streamlit 화면이 받는 값(common.api)이 같은지 본다
│  │  └─ page_numbers.py                                # ② 화면 대조: 같은 화면을 웹(8000)과 Streamlit에서 연 뒤 보이는 글자(innerText)를 저장하고, 숫자만 골라 견준다
│  ├─ views/                                            # Streamlit 화면 한 장씩 (웹과 같은 주소·순서)
│  │  ├─ check.py                                       # 내 배당 점검 (웹 app/web/src/pages/Check.tsx): ①~⑤ 문답 → ⑥ 확인 → 결과
│  │  ├─ column.py                                      # 모아의 금융 상식 칼럼 (웹 app/web/src/pages/Column.tsx, /column · /column/:id)
│  │  ├─ company.py                                     # 회사 보기 (웹 app/web/src/pages/Company.tsx, /company/:code → ?code=)
│  │  ├─ consult.py                                     # 세무상담·신고대행 신청 (웹 app/web/src/pages/Consult.tsx): 종류 → 방법 → 지점 → 날짜·시간 → 점검 결과 보내기 → 확인 → 완료(모형)
│  │  ├─ home.py                                        # 홈 (웹 app/web/src/pages/Home.tsx)
│  │  ├─ isa_irp.py                                     # ISA·IRP 안내 (웹 app/web/src/pages/IsaIrp.tsx): 금융소득 2천만 원 이하 고객에게 쓸 만한 배당 절세 계좌를 계산으로만 보여 준다
│  │  ├─ legal_privacy.py                               # Streamlit 화면: 개인정보 처리 안내(/privacy). 글은 legal_view가 웹 legal.ts와 같게 그린다
│  │  ├─ legal_terms.py                                 # Streamlit 화면: 이용약관(특약)(/terms). 글은 legal_view가 웹 legal.ts와 같게 그린다
│  │  ├─ me.py                                          # 내 정보 (웹 app/web/src/pages/Me.tsx): 로그인했다고 가정한 시연용 고객의 개인 페이지 (source/core/personas.py, api.persona)
│  │  ├─ mypage.py                                      # 마이페이지 (웹 app/web/src/pages/MyPage.tsx): 로그인한 시연용 고객의 자산관리서비스 신청 내역과 취소(모형)
│  │  ├─ story.py                                       # 데이터 이야기 (/analysis, 웹 app/web/src/pages/Story.tsx). 회사 이름 없이 집계만. 보유 종목·점검·거래 화면과 잇지 않는다
│  │  └─ wealth.py                                      # A은행 자산관리서비스 (웹 app/web/src/pages/Wealth.tsx): 서비스 소개와 PB센터 14곳 찾기. 모형 화면이다
│  ├─ web/                                              # React + TypeScript 웹 (시연 기준 화면)
│  │  ├─ public/                                        # 그대로 내보내는 파일 (그림·PDF)
│  │  │  ├─ moa/                                        # 마스코트 모아 그림
│  │  │  │  ├─ moa_base.webp                            # 마스코트 모아 그림: 기본 표정
│  │  │  │  ├─ moa_curious.webp                         # 마스코트 모아 그림: 궁금한 표정
│  │  │  │  ├─ moa_happy.webp                           # 마스코트 모아 그림: 기쁜 표정
│  │  │  │  └─ moa_sad.webp                             # 마스코트 모아 그림: 아쉬운 표정
│  │  │  └─ onepick_story_report.pdf                    # 웹 데이터 이야기에서 내려받는 분석 보고서 PDF (report/분석결과_요약보고서.pdf와 같은 내용)
│  │  ├─ src/                                           # 웹 화면 코드
│  │  │  ├─ columns/                                    # 금융 상식 칼럼 글 (갈래별)
│  │  │  │  ├─ unit1.ts                                 # 금융 상식 칼럼 1단원 '주식의 기초' 글. 형식과 원칙은 src/column.ts 맨 위 설명을 따른다.
│  │  │  │  ├─ unit10.ts                                # 금융 상식 칼럼 '회사의 시작과 끝' 단원 글. 형식과 원칙은 src/column.ts 맨 위 설명을 따른다.
│  │  │  │  ├─ unit11.ts                                # 금융 상식 칼럼 '회사 읽는 법' 단원 글(재무제표·공시). 형식과 원칙은 src/column.ts 맨 위 설명을 따른다.
│  │  │  │  ├─ unit12.ts                                # 금융 상식 칼럼 '세금 혜택 계좌' 단원 글(ISA·IRP). 형식과 원칙은 src/column.ts 맨 위 설명을 따른다.
│  │  │  │  ├─ unit2.ts                                 # 금융 상식 칼럼 2단원 '배당 더 알기' 글. 형식과 원칙은 src/column.ts 맨 위 설명을 따른다.
│  │  │  │  ├─ unit3.ts                                 # 금융 상식 칼럼 3단원 '내 소득과 세금' 글. 형식과 원칙은 src/column.ts 맨 위 설명을 따른다.
│  │  │  │  ├─ unit4.ts                                 # 금융 상식 칼럼 4단원 '고배당 분리과세' 글. 형식과 원칙은 src/column.ts 맨 위 설명을 따른다.
│  │  │  │  ├─ unit5.ts                                 # 금융 상식 칼럼 5단원 '숫자 읽기' 글. 형식과 원칙은 src/column.ts 맨 위 설명을 따른다.
│  │  │  │  ├─ unit6.ts                                 # 금융 상식 칼럼 6단원 '경제 큰 그림' 글. 형식과 원칙은 src/column.ts 맨 위 설명을 따른다.
│  │  │  │  ├─ unit7.ts                                 # 금융 상식 칼럼 7단원 '도움받기' 글. 형식과 원칙은 src/column.ts 맨 위 설명을 따른다.
│  │  │  │  ├─ unit8.ts                                 # 금융 상식 칼럼 '투자상품 알기' 단원 글. 형식과 원칙은 src/column.ts 맨 위 설명을 따른다.
│  │  │  │  └─ unit9.ts                                 # 금융 상식 칼럼 '회사의 큰일' 단원 글. 형식과 원칙은 src/column.ts 맨 위 설명을 따른다.
│  │  │  ├─ components/                                 # 여러 화면이 함께 쓰는 조각
│  │  │  │  ├─ AccountMenu.tsx                          # 위쪽 메뉴의 로그인 버튼. 로그인하지 않아도 모든 화면을 쓸 수 있고, 시연용 고객으로 로그인·바꾸기·로그아웃을 여기서 한다.
│  │  │  │  ├─ IsaIrpPick.tsx                           # 점검 결과(금융소득 2천만 원 이하)에 붙는 ISA·IRP 구간 버튼. 총급여 구간을 고르면 /api/isa-irp(core.isa_irp)로
│  │  │  │  ├─ JudgeYear.tsx                            # '2026 판정'이 어떤 배당·어느 해 세금의 판정인지 펼쳐 보는 칸 (문장은 legal.ts JUDGE_YEAR)
│  │  │  │  ├─ Search.tsx                               # 회사 찾기: 글자를 치는 동안 후보가 뜬다(↑↓·Enter·Esc). 어디서든 '/' 키로 연다.
│  │  │  │  ├─ Tournament.tsx                           # 1장 법 토너먼트 그림: 동전 638개가 요건 세 개를 지나는 움직임을 그린다(그리기는 tournamentEngine).
│  │  │  │  ├─ charts.tsx                               # 데이터 이야기 그래프. 차트 라이브러리 기본 모양을 쓰지 않고 SVG를 직접 그린다(설계 5절).
│  │  │  │  ├─ charts2.tsx                              # 데이터 이야기 추가 그래프: 증가율 기준선, 8년 움직이는 산점도, 공시 뒤 주가 탐색, 최대주주 지분, 재무 여력.
│  │  │  │  ├─ columnIcons.tsx                          # 금융 상식 칼럼 글마다 붙는 그림 기호. 글의 내용을 한눈에 떠올리게 하는 단순한 그림이다.
│  │  │  │  ├─ columnToys.tsx                           # 금융 상식 칼럼의 그림 도구. 초등학생도 손으로 움직여 보며 알 수 있게 만든 장난감 같은 그림이다.
│  │  │  │  ├─ control.tsx                              # 데이터 이야기 '대조군과 비교' 장 그래프: 우리 638곳(파랑)과 대조군(회색)을 해마다 나란히. SVG를 직접 그린다.
│  │  │  │  ├─ macro.tsx                                # 경기와 배당: 연도별 막대, 뚜렷한 짝 산점도, 상관표. 값은 서버가 저장해 둔 결과(api.ts Macro)를 그대로 쓴다.
│  │  │  │  └─ tournamentEngine.ts                      # 법 토너먼트: 회사 하나 = 동전 하나. 조세특례제한법 제104조의27 ①의 문 세 개를 라운드로 지난다.
│  │  │  ├─ pages/                                      # 웹 화면 한 장씩 (주소별)
│  │  │  │  ├─ Check.tsx                                # 내 배당 점검 (/check, 챗봇 add-on): ①~⑤ 문답 → ⑥ 확인 → 결과.
│  │  │  │  ├─ Column.tsx                               # 모아의 금융 상식 칼럼 (/column, /column/:id): 어려운 금융 용어를 쉬운 말과 그림 도구로 풀고, 조문 원문은 접어 둔다.
│  │  │  │  ├─ Company.tsx                              # 회사 보기 (/company/:code): 이 회사 동전이 법 토너먼트에서 지난 길과 2027년 최소 필요 배당.
│  │  │  │  ├─ Consult.tsx                              # 세무상담·신고대행 신청 (/consult): 종류 → 방법 → 지점 → 날짜·시간 → 점검 결과 보내기 → 확인 → 완료(모형).
│  │  │  │  ├─ Home.tsx                                 # 홈 화면(/): 회사 찾기, 2026 판정 요약, 법 토너먼트, 각 화면으로 가는 입구.
│  │  │  │  ├─ IsaIrp.tsx                               # ISA·IRP 안내 (/isa-irp): 금융소득 2천만 원 이하 고객에게 쓸 만한 배당 절세 계좌를 계산으로만 보여 준다.
│  │  │  │  ├─ Legal.tsx                                # 원픽 개인정보 처리 안내(/privacy)와 이용약관 특약(/terms). A은행(가상) 앱 애드온의 모형 문서다.
│  │  │  │  ├─ Me.tsx                                   # 내 정보 (/me): A은행 앱에 로그인했다고 가정한 시연용 고객의 개인 페이지 (source/core/personas.py, /api/personas/{id}).
│  │  │  │  ├─ MyPage.tsx                               # 마이페이지 (/mypage): 로그인한 시연용 고객의 자산관리서비스 신청 내역과 취소(모형). 내역은 이 브라우저에만 있다(applications.ts).
│  │  │  │  ├─ Story.tsx                                # 데이터 이야기 (/analysis): 회사 이름 없이 집계만. 보유 종목·점검·거래 화면과 잇지 않는다.
│  │  │  │  └─ Wealth.tsx                               # A은행 자산관리서비스 (/wealth): 서비스 소개와 PB센터 14곳 찾기. 모형 화면이다.
│  │  │  ├─ App.tsx                                     # 웹 화면의 뼈대: 위쪽 메뉴·회사 찾기·로그인 메뉴와 주소(라우트)별 화면 연결, 탭 제목.
│  │  │  ├─ api.ts                                      # FastAPI(source/api/main.py)가 돌려주는 값의 모양과 부르는 함수
│  │  │  ├─ applications.ts                             # 자산관리서비스 신청 내역(모형). 로그인한 시연용 고객별로 이 브라우저에만 남긴다(서버로 보내거나 저장하지 않음).
│  │  │  ├─ bank.ts                                     # A은행(가상) 자산관리서비스와 PB센터. 기획안의 'A은행 종합자산관리서비스'를 화면으로 보여 주는 모형 자료다.
│  │  │  ├─ checkFlow.ts                                # 내 배당 점검 챗봇의 흐름 판단: 다음에 무엇을 물을지, '내 답' 칸에 무엇을 보일지, 계산에 무엇을 보낼지, 사진을 어느 칸에 넣을지.
│  │  │  ├─ column.ts                                   # 모아의 금융 상식 칼럼: 원픽 분석에 나오는 어려운 금융 용어와 개념을 초등학생도 알 수 있게 푼 글.
│  │  │  ├─ index.css                                   # 원픽 디자인 v0.4 (archive/design_drafts/원픽_프런트_디자인_20261029.html)와 같은 토큰
│  │  │  ├─ legal.ts                                    # A은행(가상) 원픽 연계서비스의 개인정보 처리 안내와 이용약관(모형). 원픽은 은행 앱의 애드온이라
│  │  │  ├─ main.tsx                                    # 웹 시작 파일: React를 화면에 붙이고 주소 이동(BrowserRouter)과 공통 디자인(index.css)을 켠다.
│  │  │  ├─ persona.tsx                                 # 로그인했다고 가정한 시연용 고객(source/core/personas.py). 고른 사람은 이 브라우저에만 기억한다(서버에 저장하지 않음).
│  │  │  ├─ util.ts                                     # 여러 화면이 함께 쓰는 작은 도구: 금액·비율 표시, 판정 꼬리표 글자.
│  │  │  └─ vite-env.d.ts                               # / <reference types="vite/client" />
│  │  ├─ tests/                                         # 웹 점검 흐름 테스트
│  │  │  └─ checkFlow.test.ts                           # 점검 챗봇 흐름 검증 (실행: cd app/web && node --test tests/checkFlow.test.ts)
│  │  ├─ .gitignore                                     # 웹 폴더에서 Git에 올리지 않을 것 (node_modules, dist)
│  │  ├─ eslint.config.js                               # 웹 코드 검사(ESLint) 규칙
│  │  ├─ index.html                                     # 웹 첫 HTML: React 화면이 들어갈 자리와 탭 이름
│  │  ├─ package-lock.json                              # npm이 고정한 웹 패키지 버전 잠금 파일 (손으로 고치지 않음)
│  │  ├─ package.json                                   # 웹에 필요한 패키지와 실행 명령 (npm run dev·build·test)
│  │  ├─ tsconfig.app.json                              # TypeScript 설정: 화면 코드(src)용
│  │  ├─ tsconfig.json                                  # TypeScript 설정 묶음 (app·node 두 설정을 가리킴)
│  │  ├─ tsconfig.node.json                             # TypeScript 설정: vite.config.ts 같은 빌드 도구용
│  │  ├─ vercel.json                                    # Vercel 배포 설정: /api 요청을 공유 주소의 API 서버로 넘김
│  │  └─ vite.config.ts                                 # Vite 빌드 설정: 개발 중 /api 요청을 8000번 API 서버로 넘김
│  ├─ app.py                                            # 원픽 Streamlit 화면: 웹(app/web/src, React)과 같은 화면·문구·숫자를 Streamlit으로 본뜬 것
│  ├─ bank_util.py                                      # app/web/src/bank.ts의 함수(날짜·이미 찬 시간·모형 예약 번호)와 applications.ts(신청 내역)를 Python으로
│  ├─ column_icons.json                                 # 금융 상식 칼럼 그림 아이콘 모음 (export_column_assets.mjs가 웹에서 뽑아 만듦)
│  ├─ column_toys.py                                    # 금융 상식 칼럼의 그림 도구 (웹 app/web/src/components/columnToys.tsx)
│  ├─ common.py                                         # Streamlit 화면이 함께 쓰는 것: 웹과 같은 디자인(app/web/src/index.css), 웹과 같은 숫자(source/api/main.py 함수), 숫자 표시 규칙
│  ├─ export_column_assets.mjs                          # 금융 상식 칼럼(app/web/src/pages/Column.tsx)의 그림을 Streamlit에서 그대로 쓰려고 뽑는다.
│  ├─ export_web_text.mjs                               # 웹 화면(app/web/src)의 글·모형 자료를 그대로 뽑아 app/web_text.json으로 쓴다.
│  ├─ legal_view.py                                     # 개인정보 처리 안내(/privacy)와 이용약관 특약(/terms) (웹 app/web/src/pages/Legal.tsx)
│  ├─ story_charts.py                                   # 데이터 이야기 그림: 웹 app/web/src/components/charts.tsx·charts2.tsx·control.tsx·macro.tsx를 Python으로 옮긴 것
│  ├─ web_column_toys.js                                # 칼럼의 "손으로 움직이는 그림"을 Streamlit에서 그대로 돌리려고 웹 코드를 한 파일로 묶은 것 (자동 생성)
│  ├─ web_text.json                                     # 웹 화면 글(bank.ts·legal.ts·column.ts 등)을 Streamlit이 같은 문구로 쓰게 뽑아 둔 파일 (export_web_text.mjs가 만듦)
│  └─ web_tournament.js                                 # 1장 법 토너먼트 그림을 Streamlit에서 돌리려고 웹 코드를 한 파일로 묶은 것 (자동 생성)
├─ output/                                              # 코드가 만든 결과물
│  ├─ charts/                                           # 기획안·PRD 그림, 배당 여력 지도
│  │  ├─ 그림1_업무흐름도_AsIs_ToBe.jpg                 # 기획안·PRD 그림 1: 지금(As-Is)과 원픽 도입 뒤(To-Be) 업무 흐름
│  │  ├─ 그림2_기능구조도.jpg                           # 기획안·PRD 그림 2: 기능 구조도 (P0·P1·모형 구분)
│  │  ├─ 그림3_ERD.jpg                                  # 기획안·PRD 그림 3: 주요 테이블 관계도(ERD)
│  │  ├─ 그림4_서비스흐름도.jpg                         # 기획안·PRD 그림 4: 내 배당 점검 서비스 흐름과 예외 분기
│  │  ├─ 그림5_시스템구성도.jpg                         # 기획안·PRD 그림 5: 데이터가 어디서 와서 어디에 보이는지(시스템 구성도)
│  │  ├─ 그림6_WBS_간트차트.jpg                         # 기획안·PRD 그림 6: 10/19~11/05 작업 일정(WBS·간트차트)
│  │  ├─ 배당_여력_지도_2025.svg                        # 배당 여력 지도 그림 (2025년 기준, 5장 현금 여력)
│  │  └─ 배당_여력_지도_3년평균.svg                     # 배당 여력 지도 그림 (최근 3년 평균 기준)
│  ├─ screens/                                          # 웹 화면 캡처
│  │  ├─ S-01_데이터이야기.jpg                          # 웹 화면 캡처: 데이터 이야기(/analysis) 첫 부분
│  │  ├─ S-02_내배당점검_문답.jpg                       # 웹 화면 캡처: 내 배당 점검 문답
│  │  ├─ S-03_내배당점검_결과.jpg                       # 웹 화면 캡처: 내 배당 점검 결과(세액 차이·종목별 판정)
│  │  ├─ S-04_회사화면.jpg                              # 웹 화면 캡처: 회사 화면(삼성전자, 판정 세 라운드·2027 최소 필요 배당)
│  │  ├─ S-05_금융상식칼럼.jpg                          # 웹 화면 캡처: 금융 상식 칼럼
│  │  ├─ S-06_제도별비교.jpg                            # 웹 화면 캡처: 제도별 비교(ISA·IRP)
│  │  ├─ S-07_자산관리_모형.jpg                         # 웹 화면 캡처: A은행 자산관리·세무상담 신청(모형)
│  │  └─ S-08_내정보_가상고객.jpg                       # 웹 화면 캡처: 내 정보(가상 고객)
│  ├─ tables/                                           # 검토표·검산표 엑셀
│  │  ├─ B2024_배당소득_20261024.xlsx                   # 2024 사업연도 배당소득 B(2024) 확인표 (KIND 공시 값 + DART 값)
│  │  ├─ OCR_검토표_20261026.xlsx                       # 밸류업 공시 문서 OCR 결과를 사람이 확인하는 검토표
│  │  ├─ OCR_사람표본_20261027.xlsx                     # OCR 품질을 사람이 직접 비교한 표본 쪽
│  │  ├─ 밸류업_약속_자동추출_검토표_20261029.xlsx      # 밸류업 공시에서 자동으로 뽑은 배당 약속 문장 검토표 (240건)
│  │  ├─ 밸류업_정책_검토표_20261027_박예지.xlsx        # 밸류업 정책 항목 검토표 (박예지 검토판)
│  │  ├─ 원픽_분석데이터_20261025.xlsx                  # 분석에 쓴 데이터 전체를 칸별 상태와 함께 모은 엑셀
│  │  ├─ 원픽_전수검산표_20261023_검토본.xlsx           # 638사 배당·재무 전수 검산표 (팀 검토본)
│  │  ├─ 원픽_전수검산표_20261025.xlsx                  # 638사 배당·재무 전수 검산표 (10-25 다시 만든 판)
│  │  ├─ 주식총수_검산표_20261027.xlsx                  # 주식 총수(발행·자기·유통) 검산표
│  │  ├─ 증자감자_배당증감_20261026.xlsx                # 증자·감자·분할·병합 공시마다 배당이 늘었는지 본 표
│  │  └─ 증자감자_분할병합_검산표_20261023_검토본.xlsx  # 증자·감자·분할·병합 검산표 (팀 검토본)
│  └─ streamlit_screen.png                              # Streamlit 앱 첫 화면(홈) 캡처 (11-03, 638곳 중 530곳 통과 판정 요약)
├─ report/                                              # 문서
│  ├─ PRD/                                              # 제출 문서: PRD
│  │  └─ 1조_종합프로젝트_PRD_261103_v1.0.docx          # 제출용 PRD v1.0 (과정 원본 양식 위에 작성)
│  ├─ 검증/                                             # 원문 대조·세액·조문 검증 기록
│  │  ├─ DART_불일치_검토표.csv                         # DART 값과 원문이 다른 칸 목록 (사람 검토용)
│  │  ├─ DART_빈칸_채우기_결과.md                       # DART 원문으로 DB 빈칸 채우기 결과
│  │  ├─ DART_원문대조_재무제표_결과.md                 # DART 원문 대조 결과 — 재무제표
│  │  ├─ Streamlit_웹_대조_결과.md                      # Streamlit 화면과 웹 화면 대조 결과 (2026-11-02)
│  │  ├─ 데이터_교체_예정.md                            # 원천 데이터 교체 예정
│  │  ├─ 별도재무제표_보완자료_확인요청.md              # 03 별도재무제표 보완 자료 확인 요청
│  │  ├─ 별도재무제표_원문대조_결과.csv                 # 별도재무제표 값을 사업보고서 원문과 대조한 결과
│  │  ├─ 보류_데이터_최종_처리_결과.md                  # 보류 데이터 최종 처리 결과와 시스템 반영 여부
│  │  ├─ 세액계산_ISA_IRP_검증_결과.md                  # 세액 계산 · ISA·IRP 규칙 검증 결과
│  │  ├─ 인공지능기본법_검토.md                         # 인공지능기본법 관련 검토 (챗봇 add-on)
│  │  ├─ 조문_코드_대응표.md                            # 조문 ↔ 코드 대응표
│  │  ├─ 챗봇_종목해석_정답률.md                        # 챗봇 보유 종목 해석 정답률 (2026-10-26)
│  │  └─ 최종_점검_결과_20261104.md                     # 제출 전 최종 점검: 판정·세액·ISA·IRP 기준 대조, 오늘 고친 것, 시연용 모형과 실제 구현 구분
│  ├─ 기획안/                                           # 제출 문서: 기획안
│  │  └─ 1조_종합프로젝트_기획안_261103.docx            # 제출용 기획안 (11-03 웹 구현 기준)
│  ├─ 분석/                                             # 장별 분석 결과 (md·csv)
│  │  ├─ 공시시기_최대주주_비교_결과.md                 # 공시 시기·최대주주 비교 — 누가 25% 기준선에 맞췄나
│  │  ├─ 기준선_몰림_분석_결과.md                       # 25% 기준선 쏠림 분석 결과 — 배당성향이 25% 바로 위에 몰렸나
│  │  ├─ 대조군_비교분석_20261102.md                    # 우리 638사 vs 4조 대조군 비교 분석
│  │  ├─ 무리별_주가_비교_결과.md                       # 무리별 주가 비교 — 638사 안에서 어느 쪽 주가가 더 올랐나
│  │  ├─ 배당_거시지표_상관_결과.md                     # 배당과 거시지표의 상관 결과
│  │  ├─ 배당_거시지표_상관_시차.csv                    # 8장 경기와 배당: 시차별 상관 결과
│  │  ├─ 배당_거시지표_상관_연도.csv                    # 8장 경기와 배당: 연도 값끼리 상관 결과
│  │  ├─ 배당_거시지표_상관_연도차이.csv                # 8장 경기와 배당: 전년 대비 차이로 본 상관 결과
│  │  ├─ 배당_거시지표_상관_회사연도.csv                # 8장 경기와 배당: 회사·연도 단위 상관 결과
│  │  ├─ 배당_거시지표_연도표.csv                       # 8장 경기와 배당: 연도별 거시지표·배당 지표 표
│  │  ├─ 배당_노출도_분석_결과.csv                      # 금리·환율 노출도와 배당 방향 분석 결과 표
│  │  ├─ 배당_노출도_분석_결과.md                       # 금리·환율 노출도와 배당 결정 (회사×연도 패널)
│  │  ├─ 배당_여력_지도_결과.md                         # 배당 여력 지도 — 2027년에 더 내야 하는 배당을 낼 현금이 있나
│  │  ├─ 배당_제도효과_분석_결과.csv                    # 9장 세금 제도와 배당(이중차분) 결과 표
│  │  ├─ 배당_제도효과_분석_결과.md                     # 고배당기업 배당소득 분리과세는 배당 결정을 바꿨나 (이중차분)
│  │  ├─ 배당성향_변화_분해_결과.md                     # 배당성향 변화 나눠 보기 — 25%를 배당을 늘려서 넘겼나, 순이익이 줄어서 넘겼나
│  │  ├─ 밸류업_고배당공시_주가반응_결과.md             # 밸류업 계획·고배당기업 공시 뒤 주가 반응
│  │  ├─ 밸류업_약속_분류_결과.md                       # 밸류업 계획 약속 분류 — 638사는 무엇을 약속했나
│  │  ├─ 밸류업_약속_실제_결과.md                       # 밸류업 약속과 실제 — 2025년 말까지 한 약속을 2025 사업연도에 지켰나
│  │  ├─ 분석_가정과_한계.md                            # 분석마다 가정과 한계 (데이터 이야기 화면)
│  │  ├─ 업종_위치_주가수준_결과.md                     # 업종 안 위치와 주가 수준 — 수익성·안정성(B3), 배당수익률·PBR(C3)
│  │  ├─ 유지가능성_분석_결과.md                        # 고배당기업 유지 가능성 — 올해 충족한 회사가 내년에도 충족할까
│  │  ├─ 이벤트스터디_방법별_결과.md                    # 이벤트 스터디 방법별 결과
│  │  ├─ 이벤트스터디_유의성_보고서.pdf                 # 6장 이벤트 스터디 검정 결과를 색으로 구분한 보고서
│  │  └─ 판정_보류_정리.md                              # 판정 보류 정리 — 어느 회사가, 왜 보류됐나
│  ├─ 설계/                                             # DB·화면·챗봇 설계
│  │  ├─ 1조_ERD설계서_261104.docx                      # ERD 설계서: 표 61개·보기 13개의 구조·관계·키, 행 수 (11-04 DB 기준)
│  │  ├─ 1조_시스템설계서_261104.docx                   # 시스템 설계서: 구성·데이터 흐름·서버·화면·AI·검증 (11-04)
│  │  ├─ 1조_조문코드대응표_검토법령_261104.docx        # 조문 ↔ 코드 대응표와 검토한 법령 (제출용 문서)
│  │  ├─ 1조_화면설계서_261104.docx                     # 화면 설계서: 화면마다 구성·입력·API·고지 문구·이동 (11-04 코드와 배포 화면 기준)
│  │  ├─ DB_ERD_전체.pdf                                # onepick DB 전체 표 관계도(ERD)
│  │  ├─ 데이터_분석_설계.md                            # 데이터 분석 설계 — onepick DB로 무엇을, 어떻게 분석할까
│  │  ├─ 챗봇_설계_초안.md                              # 챗봇 설계 초안 v0.2 (2026-10-27)
│  │  ├─ 챗봇_질문목록.md                               # 챗봇이 답해야 할 질문 목록 (2026-10-29)
│  │  └─ 프런트엔드_설계.md                             # 프런트엔드 설계: Streamlit 밖으로 (v0.3, 모아 디자인)
│  ├─ 실행안내/                                         # 팀원 실행·배포·시연 절차
│  │  ├─ 배포_안내.md                                   # 시연판 배포 안내 (Vercel + 이 Mac)
│  │  ├─ 시연_점검과_예비_실행_절차.md                  # 시연 점검 결과와 예비 실행 절차
│  │  └─ 팀원_실행_안내.md                              # 원픽 팀원 실행 안내
│  └─ 분석결과_요약보고서.pdf                           # 데이터 이야기 11장 분석 결과 요약 보고서 (목적·방법·결과·한계)
├─ presentation/                                        # 발표 자료
│  ├─ ~$파이널프로젝트_발표자료.pptx
│  └─ 파이널프로젝트_발표자료.pptx                      # 최종 발표 자료 42장 (기획 배경·데이터 이야기 화면·분석 결과 전부·인사이트·챗봇 로직·개발 프로세스·팀, 글꼴 맑은 고딕)
└─ archive/                                             # 지금은 안 쓰지만 기록으로 남긴 파일 (코드·화면이 부르지 않음)
   ├─ design_drafts/                                    # 10-27~29 디자인 시안 (디자인 확정 뒤 안 씀)
   │  ├─ 모아_시안_원본/                                # 모아 시안 원본
   │  │  ├─ moa/                                        # 시안용 모아 그림
   │  │  │  ├─ moa_base.webp                            # 마스코트 모아 그림: 기본 표정
   │  │  │  ├─ moa_curious.webp                         # 마스코트 모아 그림: 궁금한 표정
   │  │  │  ├─ moa_happy.webp                           # 마스코트 모아 그림: 기쁜 표정
   │  │  │  └─ moa_sad.webp                             # 마스코트 모아 그림: 아쉬운 표정
   │  │  ├─ build.py                                    # 모아 시안 HTML 만들기: 숫자는 모두 core 계산 결과에서, 모아 그림은 MASCOT_DIR에서 넣는다
   │  │  └─ template.html                               # 모아 마스코트 시안을 만들던 HTML 틀 (10-28, 디자인 확정 뒤 안 씀)
   │  ├─ 프런트_디자인_원본/                            # 프런트 시안 원본
   │  │  ├─ build.py                                    # 프런트 디자인 v0.4 HTML 만들기: 숫자는 모두 DB·core 계산 결과에서, 그래프는 SVG로 그려 넣는다
   │  │  └─ template.html                               # 프런트 디자인 시안을 만들던 HTML 틀 (10-29, 디자인 확정 뒤 안 씀)
   │  ├─ 원픽_디자인시안_20261027.html                  # 10-27 첫 디자인 시안 (스케일업안으로 고정되며 안 씀)
   │  ├─ 원픽_모아_시안_20261028.html                   # 10-28 모아 마스코트 시안
   │  ├─ 원픽_프런트_디자인_20261029.html               # 10-29 프런트 디자인 v0.4 시안 (웹 index.css 색·글꼴의 출처)
   │  └─ 원픽_화면_새디자인시안_20261027.pdf            # 10-27 새 디자인 시안 PDF
   ├─ old_docs/                                         # 새 문서로 바뀐 옛 문서
   │  ├─ DB_스키마_구조도_20261026.pdf                  # 10-26 DB 스키마 구조도 (표 35개 때 그림, 지금은 report/설계/DB_ERD_전체.pdf)
   │  ├─ 기획안_대비_현황.md                            # 기획안 대비 현황
   │  ├─ 분석_방법과_가정.md                            # 분석 방법과 가정 — 무엇을, 어떻게, 어떤 가정으로 계산했나
   │  ├─ 스케일업_구상.md                               # 스케일업 구상
   │  └─ 확장_제안_10선_개인화_사용자경험.md            # 원픽 확장 제안 10선 — 개인화 · 사용자 경험
   ├─ old_sample/                                       # 처음 만든 예시
   │  ├─ hello.py                                       # 처음 환경을 맞출 때 만든 예시 스크립트 (인사말 출력)
   │  └─ test_hello.py                                  # 처음 환경을 맞출 때 만든 예시 테스트 (hello.py용)
   ├─ old_screens/                                      # 옛 화면 캡처
   │  └─ 원픽_웹화면_전체캡처_20261029.pdf              # 10-29 웹 화면 전체 캡처 (그 뒤 화면이 많이 바뀌어 옛 기록)
   ├─ old_streamlit_ui/                                 # 11-02 이전 옛 Streamlit 화면 조각
   │  ├─ assets/                                        # 옛 Streamlit 그림
   │  │  ├─ pick/                                       # 옛 마스코트 픽이
   │  │  │  ├─ props/                                   # 픽이 소품 그림
   │  │  │  │  ├─ acorn.png                             # 옛 Streamlit 마스코트 픽이 그림 조각: acorn
   │  │  │  │  ├─ jar_empty.png                         # 옛 Streamlit 마스코트 픽이 그림 조각: jar_empty
   │  │  │  │  ├─ tree_gray.png                         # 옛 Streamlit 마스코트 픽이 그림 조각: tree_gray
   │  │  │  │  ├─ tree_green.png                        # 옛 Streamlit 마스코트 픽이 그림 조각: tree_green
   │  │  │  │  └─ tree_red.png                          # 옛 Streamlit 마스코트 픽이 그림 조각: tree_red
   │  │  │  ├─ web/                                     # 픽이 웹용 그림
   │  │  │  │  ├─ acorn.webp                            # 옛 Streamlit 마스코트 픽이 그림 조각: acorn
   │  │  │  │  ├─ base.webp                             # 옛 Streamlit 마스코트 픽이 그림 조각: base
   │  │  │  │  ├─ blink.webp                            # 옛 Streamlit 마스코트 픽이 그림 조각: blink
   │  │  │  │  ├─ body.webp                             # 옛 Streamlit 마스코트 픽이 그림 조각: body
   │  │  │  │  ├─ curious.webp                          # 옛 Streamlit 마스코트 픽이 그림 조각: curious
   │  │  │  │  ├─ head.webp                             # 옛 Streamlit 마스코트 픽이 그림 조각: head
   │  │  │  │  ├─ hop.webp                              # 옛 Streamlit 마스코트 픽이 그림 조각: hop
   │  │  │  │  ├─ jar.webp                              # 옛 Streamlit 마스코트 픽이 그림 조각: jar
   │  │  │  │  ├─ sad.webp                              # 옛 Streamlit 마스코트 픽이 그림 조각: sad
   │  │  │  │  ├─ tail.webp                             # 옛 Streamlit 마스코트 픽이 그림 조각: tail
   │  │  │  │  ├─ tree_gray.webp                        # 옛 Streamlit 마스코트 픽이 그림 조각: tree_gray
   │  │  │  │  ├─ tree_green.webp                       # 옛 Streamlit 마스코트 픽이 그림 조각: tree_green
   │  │  │  │  └─ tree_red.webp                         # 옛 Streamlit 마스코트 픽이 그림 조각: tree_red
   │  │  │  ├─ 01_base.png                              # 옛 Streamlit 마스코트 픽이 그림 조각: 01_base
   │  │  │  ├─ 02_body_no_tail.png                      # 옛 Streamlit 마스코트 픽이 그림 조각: 02_body_no_tail
   │  │  │  ├─ 03_tail.png                              # 옛 Streamlit 마스코트 픽이 그림 조각: 03_tail
   │  │  │  ├─ 04_eyes_closed.png                       # 옛 Streamlit 마스코트 픽이 그림 조각: 04_eyes_closed
   │  │  │  ├─ 05_sad.png                               # 옛 Streamlit 마스코트 픽이 그림 조각: 05_sad
   │  │  │  ├─ 06_curious.png                           # 옛 Streamlit 마스코트 픽이 그림 조각: 06_curious
   │  │  │  ├─ 07_hop.png                               # 옛 Streamlit 마스코트 픽이 그림 조각: 07_hop
   │  │  │  └─ reference.png                            # 옛 마스코트 픽이 참고 그림
   │  │  ├─ avatar_bot.png                              # 옛 Streamlit 챗봇 말풍선 그림
   │  │  └─ avatar_user.svg                             # 옛 Streamlit 사용자 말풍선 그림
   │  ├─ charts.py                                      # 기준선 계단 그래프: 1%p 구간 분포를 기준선(25%·40% 등)으로 나눈 구역 위에 막대로 그린다
   │  ├─ mascot.py                                      # 마스코트 '픽이'(도토리를 안은 3D 다람쥐)와 도토리 그림. HTML·SVG 문자열만 만든다
   │  └─ test_mascot.py                                 # 옛 Streamlit 마스코트·그래프 조각(mascot.py·charts.py) 테스트
   └─ old_tables/                                       # 새 판으로 바뀐 옛 날짜 엑셀
      ├─ 밸류업_정책_검토_20261027_박예지.zip           # 밸류업 정책 검토표 10-27판을 묶은 압축 파일 (같은 xlsx가 output/tables에 있음)
      ├─ 밸류업_정책_검토표_20261025.xlsx               # 밸류업 정책 검토표 10-25판 (10-27 박예지 검토판으로 바뀜)
      ├─ 원픽_분석데이터_20261023.xlsx                  # 분석 데이터 엑셀 10-23판 (10-25판으로 바뀜)
      └─ 원픽_전수검산표_20261023.xlsx                  # 전수 검산표 10-23판 (팀 검토본·10-25판으로 바뀜)
```

## 처음 한 번 (설치)

맨 위 폴더에서 실행합니다. requirements.txt 안의 `-e ./source`가 `source/` 코드를 설치해서, 어느 폴더에서든 `python -m scripts.이름`이 됩니다.

```bash
.venv/bin/python -m pip install -r requirements.txt
```

```bash
npm --prefix app/web install
```

## 실행

시연할 때(서버 하나, 화면은 http://127.0.0.1:8000): 웹을 빌드해 두면 API 서버가 화면까지 띄웁니다. DB(`onepick`)가 켜져 있어야 숫자가 나옵니다.

```bash
npm --prefix app/web run build && .venv/bin/python -m scripts.run_api
```

개발할 때(창 두 개, 화면은 http://127.0.0.1:5173):

```bash
.venv/bin/python -m scripts.run_api
```

```bash
cd app/web && npx vite --host 127.0.0.1
```

Streamlit 화면(웹과 같은 글·숫자, 8000 서버 없이 API 함수를 바로 부름):

```bash
.venv/bin/streamlit run app/app.py
```

테스트:

```bash
.venv/bin/python -m pytest source/tests -q
```

### 챗봇 입력 해석과 조문 찾기의 AI (선택)

- **입력 해석**: 규칙으로 못 읽은 문장만 이 컴퓨터의 Ollama `qwen3.5:4b`(Apache 2.0)로 해석합니다(`ollama pull qwen3.5:4b`). 모델이 없거나 Ollama가 꺼져 있으면 규칙만으로 읽고, 못 읽으면 다시 묻습니다. 끄기 `ONEPICK_OLLAMA=0`, 모델 바꾸기 `ONEPICK_OLLAMA_MODEL=이름`.
- **관련 조문 찾기**: 이 컴퓨터의 Ollama `bge-m3`로 질문과 조문을 비교합니다(`ollama pull bge-m3`). Ollama가 꺼져 있으면 글자 검색으로 찾습니다. 조문은 원문 그대로만 보여 줍니다.
  찾는 조문 목록은 `source/core/law_search.py`의 `SOURCES`, 다시 받기: `.venv/bin/python -m core.law_search build`
- 주소는 localhost만 허용하며, 고객 입력을 외부로 보내지 않습니다.

## 분석 DB (PostgreSQL, PRD v0.2 6.2)

이 컴퓨터의 PostgreSQL(Postgres.app)에 `onepick` DB를 만들고 원천 엑셀(01~09)을 적재합니다. 주소는 `DATABASE_URL`(기본 `postgresql://localhost/onepick`)로 바꿀 수 있습니다.

```bash
.venv/bin/python -m scripts.load_raw
```

```bash
.venv/bin/python -m scripts.load_review_workbook output/tables/원픽_전수검산표_20261023_검토본.xlsx --capital output/tables/증자감자_분할병합_검산표_20261023_검토본.xlsx
```

```bash
.venv/bin/python -m scripts.build_core
```

```bash
.venv/bin/python -m scripts.load_prices
```

```bash
.venv/bin/python -m scripts.collect_macro && .venv/bin/python -m scripts.load_macro
```

- 거시지표(경상수지·기준금리·국고채 3년·원/달러·GDP·CPI·실업률·고용률, 2016~)는 한국은행 ECOS에서 받아 `data/raw/macro/`에 두고 `raw.ecos_macro`에 넣습니다. 키는 `.env`의 `ECOS_API_KEY`.
- 배당과 거시지표의 상관은 `.venv/bin/python -m scripts.analyze_macro_dividend`(약 3분)로 계산해 `core.core_macro_dividend_*` 표와 `report/분석/배당_거시지표_상관_결과.md`에 남기고, 데이터 분석 화면 "거시지표와 배당" 탭이 그 표를 읽습니다.

- 원천 폴더 기본값: `data/raw/원천엑셀` (없으면 예전 위치 `~/찐파이널/raw/고배당 관련 데이터`, `--source`로 바꾸기). 엑셀 원본은 git에 넣지 않습니다.
- `raw`(원천 그대로) → `core`(회사·연도 가공, 판정·최소액) → `ref`(세율표). 표 정의는 `source/db/schema.sql`, 열 대응은 `report/검증/조문_코드_대응표.md` 9절.
- 두 스크립트는 다시 돌리면 표를 비우고 새로 채웁니다. 그래서 `load_raw` 다음에는 팀이 원문을 보고 확정한 검토본을 `load_review_workbook`으로 다시 넣습니다(`report/검증/데이터_교체_예정.md`).
- B(배당소득)는 '미산출'이라 판정·최소액은 지금 모두 '판정 보류'입니다.
- **회사 범위는 638사로 확정했습니다**(에코마케팅은 2026-06-15 상장폐지로 제외). 남은 결측 보완 항목 → `report/검증/데이터_교체_예정.md`
- KRX 주가(`data/raw/krx/prices.csv`)와 시장지수(`market.csv`, KOSPI·KOSDAQ)는 한국거래소(KRX) 시세를 pykrx로 받은 일별 수정 종가입니다. 알려진 문제와 다시 넣는 법 → `report/검증/데이터_교체_예정.md`

### DB를 다른 사람에게 넘기기

원천 엑셀 없이도 같은 DB를 쓸 수 있게 DB 전체를 파일로 넘깁니다. 방법은 두 가지이고, 파일은 모두 git에 넣지 않습니다.

**DuckDB 파일 하나 (제출용, 권장)**: `data/db/onepick_오늘날짜.duckdb` 하나에 모든 표·보기 값(DuckDB로 바로 읽기), PostgreSQL 스키마 SQL, 열마다 원래 자료형, 표마다 행 수·확인값이 들어 있습니다. 이 파일만으로 PostgreSQL을 되살릴 수 있습니다.

```bash
.venv/bin/python -m scripts.export_duckdb
.venv/bin/python -m scripts.restore_duckdb data/db/onepick_20261103.duckdb
```

- 되살리면 표 61개마다 행 수와 확인값(행 값을 글자로 바꾼 md5의 합)을 뽑을 때와 대조하고, 하나라도 다르면 실패로 끝납니다. numeric은 값이 같으면 같다고 봅니다(소수 끝 0 표기는 달라질 수 있음).
- 넣는 동안 외래키 순서 검사를 잠시 끄므로 PostgreSQL 슈퍼유저 계정이 필요합니다. `--replace`, `--url`은 아래 덤프 방법과 같습니다.
- DuckDB에서 바로 보기: `duckdb data/db/onepick_20261103.duckdb "select * from core.core_judgement_2026 limit 5"`. 무엇이 들었는지는 `main._about`(표·행 수)·`main._columns`(자료형) 표에 있습니다.

**덤프 + 확인표**: 덤프(`.dump`)와 확인표(`.json`) 두 파일을 함께 전달합니다.

**넘기는 사람**: `data/db/onepick_오늘날짜.dump`와 `.json`이 생깁니다.

```bash
.venv/bin/python -m scripts.export_db
```

**받는 사람**: PostgreSQL 17 이상과 이 저장소가 필요합니다. 코드는 확인표의 `git_commit`과 같은 커밋으로 맞추세요. 두 파일을 `data/db/` 폴더에 두고 실행하면 `onepick` DB를 만들고 되살린 뒤, 표마다 행 수와 판정 집계가 뽑을 때와 같은지 대조합니다.

```bash
.venv/bin/python -m scripts.restore_db
```

- 다른 곳에 둔 덤프는 경로를 붙입니다: `scripts.restore_db 받은폴더/onepick_20261029.dump` (같은 이름의 `.json`이 옆에 있어야 함).
- `onepick` DB가 이미 있으면 멈춥니다. 지우고 다시 만들려면 `--replace`를 붙입니다(기존 내용은 사라짐).
- 다른 이름이나 다른 서버로 되살리려면 `--url postgresql://주소/이름`. 앱도 같은 주소를 `DATABASE_URL`로 주면 됩니다.
- 챗봇 AI(Ollama `qwen3.5:4b`·`bge-m3`)는 선택입니다. 없으면 규칙과 글자 검색으로 돌아갑니다.
- 정책 문서 원본 PDF(`data/raw/policy_docs`, 약 1.3GB)는 화면에 필요 없습니다. 글자는 DB에 들어 있고, OCR을 다시 돌릴 때만 씁니다.

## 계산 엔진 (`source/core/`, 기획안·PRD 기준)

| 모듈 | PRD | 내용 |
|---|---|---|
| `judgement.py` | F-01 | 고배당기업 요건 판정(충족·미충족·판정 보류, 가목·나목, 사유, 조문) |
| `min_dividend.py` | F-02 | 2027 사업연도 유지에 필요한 최소 배당액, 순이익 시나리오, 추가 필요액 |
| `valueup.py` | F-03 | 밸류업 배당 목표 환산과 최소액 비교(이상·미만·비교 불가) |
| `tax_rates.py`, `tax.py` | F-04 | 세율표(시행일·출처), 분리과세 세액 S(E)와 신청 전후 세액 차이 T0 − (T1 + S(E)) |
| `event_study.py` | F-05 | 공시 후 20·60거래일 누적 초과수익률, 공시 종류별 중앙값·범위·사례 수 |

- 금액은 모두 원 단위 정수로 계산하고, 비율은 나누지 않고 곱해서 비교합니다.
- `tax_rates.py`의 세율은 '확인 필요' 상태입니다. 법령 현행본과 대조한 뒤 '원문 확인'으로 바꿔 주세요.

## 외부 자료 수집과 결측 보완 (`source/core/sources/`)

화면에서는 보이는데 API로 받으면 비는 값을 줄이고, 끝까지 못 찾은 값은 0으로 채우지 않고 사유와 함께 남깁니다.
수집은 원천마다 따로 쓰는 구글 코랩 노트북으로 합니다. 노트북마다 돌리는 사람이 달라도 되고, 각 노트북은 필요한 `source/core/sources` 코드를 담고 있어 코랩에서 **런타임 → 모두 실행** 한 번이면 됩니다.

- 시작할 때 구글 드라이브를 연결해 저장 폴더에 써 보고, 키를 실제로 한 번 불러 확인합니다. 문제가 있으면 그 자리에서 멈춥니다.
- 끝나면 결과를 `<노트북>_<날짜_시간>.zip`으로 묶어 각자 **내 드라이브 `ONE_PICK_결과/`**에 넣습니다. 팀에 넘길 때는 그 zip을 직접 올립니다.
- 진행 기록·응답 원본은 내 드라이브 `ONE_PICK_data/`에 남아 다음 날 이어서 돌릴 수 있습니다.

| 노트북 | 하는 일 | 키(비밀 입력) |
|---|---|---|
| [`01_기업_매핑표_만들기`](source/notebooks/01_기업_매핑표_만들기.ipynb) | KIND 밸류업 고배당기업 목록(639사, 종목코드 없음·회사명은 KRX 약칭)에 DART 고유번호·종목코드·시장구분·결산월·업종을 붙여 `company_map.csv`를 만듦 | `DART_API_KEY` |
| [`02_연결재무제표_수집`](source/notebooks/02_연결재무제표_수집.ipynb) | 연결감사보고서 원문 기준 재무 값 + 사업보고서 API 대조, 배당 표 (연결), 배당 결정 공시, 주식 총수·최대주주 | `DART_API_KEY` |
| [`03_별도재무제표_수집`](source/notebooks/03_별도재무제표_수집.ipynb) | 감사보고서 원문 기준 재무 값 + 사업보고서 API 대조, 배당 표 (별도) | `DART_API_KEY` |
| [`04_KRX_시세_수집`](source/notebooks/04_KRX_시세_수집.ipynb) | 수정주가·시장지수(유가→코스피, 코스닥→코스닥 지수), 거래정지 구분 | `KRX_ID`, `KRX_PW` (pykrx가 KRX 로그인을 요구함) |
| [`05_법령_원문_수집`](source/notebooks/05_법령_원문_수집.ipynb) | 조문 원문 → `articles.json` | `LAW_OC` |

01 담당자가 `company_map.csv`를 02·03·04 담당자에게 넘기면, 받은 사람은 자기 `ONE_PICK_결과/`에 넣거나 실행 중 업로드 창으로 올립니다. 05는 따로 돌립니다.

- 재무 값은 **감사보고서 원문**이 기본이고, 사업보고서 API 값은 대조용입니다(`일치`·`불일치`·`API 값 없음`).
- 계정 정의(`opendart.ACCOUNTS`)는 재무회계 팀원 검토를 반영했습니다. 연결↔별도, 다른 계정으로의 자동 대체는 하지 않습니다.
- `source/core/sources`를 고치면 노트북 안의 코드도 다시 만들어야 합니다(노트북은 코드 사본을 담고 있음).

| 모듈 | 원천 | 보완하는 결측 |
|---|---|---|
| `base.py` | 공통 | 결측 상태 6가지, `'-'`·`△`·쉼표 숫자 변환, 재시도, 원본 캐시(`data/raw/`), 비밀키 입력, 하루 한도 이어받기 |
| `opendart.py` | OpenDART | status 코드, 감사보고서 원문 재무제표 읽기(단위·주석 칸·당기/전기 칸), 계정별 허용 재무제표, account_id→계정 이름, 다음 해 전기 값, 배당 항목 단위·주식 종류, 공시 쪽 넘김·최종본, 원문 표, 주식 총수, 최대주주 |
| `krx.py` | KRX·pykrx | 종목코드 6자리, 휴장일/거래정지/상장 전 구분, 거래정지일은 비워 둠, 시장별 지수 짝짓기 |
| `law.py` | 국가법령정보센터 | 항·호·목이 하나일 때 dict, 중첩 목록, 조문가지번호, 실패 시 보관본 |
| `kind.py` | KIND 엑셀 | HTML로 된 `.xls`(cp949), 종목코드 앞자리 0, 열 이름 차이, 사업연도 이상, 회사명(약칭)→DART 고유번호 매핑표(`build_company_map`) |
| `samples.py` | 가짜 응답 | 테스트와 노트북의 '키 없이 작동 확인' 셀용 |

- API 키는 **비밀 입력**(`getpass`)으로 받습니다. 환경변수·Colab 보안 비밀에 `DART_API_KEY`, `LAW_OC`가 있으면 그 값을 씁니다. 키는 메모리에만 두고 파일·출력·캐시 이름에 남기지 않습니다.
- 수집용 패키지: `uv pip install --python .venv/bin/python -e "./source[collect]"`
