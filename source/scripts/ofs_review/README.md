# 별도재무제표 보완 자료(03) 원문 대조

`03_별도재무제표_실제보완_감사보고서제출_20261023.zip`을 점검하고 DART 원문과 맞춰 본 코드입니다.
산출물: `report/검증/별도재무제표_보완자료_확인요청.md`, `report/검증/별도재무제표_원문대조_결과.csv`.

준비: zip을 풀어 `03_별도재무제표_수집/` 안의 내용을 `data/raw/03_별도보완/`에 둡니다(git 제외).
원문은 `data/raw/dart_cache/`(source/core/dart_doc.py와 같은 캐시), 중간 결과는 `data/raw/ofs_review/`에 저장합니다.

실행 순서 (프로젝트 폴더에서):

```bash
.venv/bin/python -m scripts.ofs_review.verify_mismatch     # API·원문 불일치 칸: 원문 문서의 감사 대상 회사·당기 값 확인
.venv/bin/python -m scripts.ofs_review.verify_own_year     # 결론 안 난 칸: 그 연도 사업보고서 별도 재무제표로 재확인
.venv/bin/python -m scripts.ofs_review.final_verdict       # 두 확인을 합쳐 칸별 최종 판정 (배당 지급 부호·단위 반올림 반영)
.venv/bin/python -m scripts.ofs_review.verify_ni           # 감사보고서 순이익 vs 배당 표 순이익 차이 칸
.venv/bin/python -m scripts.ofs_review.make_request_md data/raw/03_별도보완 report/검증/별도재무제표_보완자료_확인요청.md data/raw/ofs_review/final_verdict.csv
.venv/bin/python -m scripts.ofs_review.export_result_csv
```

`dartdoc.py`는 이 작업 때 만든 원문 읽기 도우미입니다. 이후 DB 빈칸 채우기·전수 대조는 이를 정리한 `source/core/dart_doc.py`를 씁니다.
