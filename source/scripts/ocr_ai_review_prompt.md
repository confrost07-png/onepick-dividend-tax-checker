<!-- source/scripts/ocr_ai_review.py 의 AI 검토 묶음마다 하위 에이전트에게 주는 지시문. NNN = 묶음 번호 3자리, N = 앞 0 뺀 번호 -->

You are reviewing OCR output against page images for a Korean financial-document database. Work in /Users/geummingwon/Desktop/FINAL_PROJECT_ONE_PICK/.claude/worktrees/hyo-15289f. Do not edit any code or other files; only run the record command below.

Your batch: data/raw/ocr_ai/batch_NNN.json (a JSON list of pages). Each item has "key", "image" (absolute PNG path), "low_lines" (lines the OCR engine was unsure of — check these first), and "ocr_text" (the OCR output). Read the batch file with the Read tool (read it in parts if long). If data/raw/ocr_ai/result_NNN.jsonl already exists, skip pages whose key is already recorded there.

For EACH page, in order:
1. Look at the image with the Read tool.
2. Compare it with ocr_text. Reading order and line breaks do NOT matter. Ignore pure decoration glyphs (bullets ■ □ ● • ▶ ✓, underscores or dashes used as legend markers, box borders). Everything else matters: every Korean word, English word, hanja, symbol with meaning (%, ≥, ÷, 末), and especially every number, percent, date, unit, and footnote marker like (*1).
3. Decide:
   - "확인완료": all real text in the image is present in ocr_text with the same characters.
   - "정정함": some text is wrong or missing. Give fixes as
       "edits": [{"from": "<exact substring of ocr_text that is wrong>", "to": "<what the image shows>"}]
     "from" must be copied EXACTLY from ocr_text (it is checked; include surrounding context if the wrong string is short or appears more than once, because only the first occurrence is replaced; edits apply in order). For text in the image that OCR missed entirely, use "add": ["<missing line>", ...]. For junk OCR lines that do not exist in the image, use an edit with "to": "". When a table or chart is badly scrambled, you may replace the whole scrambled span with a clean row-by-row rewrite.
   - "확인불가": the image itself is too blurry/cut to read; explain in "note".
   Transcribe what the image shows, even if the original document has a typo (keep the typo; mention "원문 오타로 보임" in note). If OCR "corrected" a typo that is in the image, edit it back to the image's spelling.
   Text inside charts (data labels, bar values, legends) counts; axis tick labels may be skipped (say so in note).
4. Record each page right after reviewing it (so progress survives interruption), by piping JSON to:
   .venv/bin/python -m scripts.ocr_ai_review record N <<'JSON'
   {"key": "...", "status": "...", "edits": [...], "add": [...], "note": "..."}
   JSON
   where N is your batch number without leading zeros. If it prints "거절" (rejected), fix the JSON (usually "from" not copied exactly) and record again.

Be accurate rather than fast; numbers matter most. Do every page in the batch. At the end, run `.venv/bin/python -m scripts.ocr_ai_review status | grep " NNN:"` and reply with ONE short Korean line: the status line plus the single most important numeric correction (from → to). Nothing else.
