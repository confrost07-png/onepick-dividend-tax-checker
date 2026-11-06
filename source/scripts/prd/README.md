# PRD docx 수정 도우미

PRD v0.1 → v0.2 수정사항(2026-10-22)을 Word 문서에 반영할 때 쓴 코드입니다. docx를 풀어 `word/document.xml`을 고칩니다.

```bash
.venv/bin/python source/scripts/prd/paras.py <풀어둔폴더>/word/document.xml 638사 고배당   # 단어가 들어 있는 문단 번호·글 찾기
.venv/bin/python source/scripts/prd/edit_prd.py <풀어둔폴더>/word/document.xml             # 수정사항 반영 (바꿀 글이 정확히 기대한 횟수만큼 있어야 진행)
```

반영 뒤 다시 압축해 `report/PRD/1조_종합프로젝트_PRD_261022_v0.2.docx`를 만들었습니다(원래 폴더, 11-03에 지움 · Git 기록에 남아 있음).
