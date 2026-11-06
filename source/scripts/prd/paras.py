"""PRD 원본 양식(docx)의 document.xml에서 찾는 낱말이 든 문단 번호와 글을 찍는다 (양식 칸 번호 찾기용)."""
import re,sys
x=open(sys.argv[1],encoding='utf-8').read()
paras=re.findall(r'<w:p[ >].*?</w:p>',x,flags=re.S)
kw=sys.argv[2:]
for i,p in enumerate(paras):
    t=''.join(re.findall(r'<w:t(?: [^>]*)?>([^<]*)</w:t>',p))
    if any(k in t for k in kw):
        print(i, repr(t[:220]))
