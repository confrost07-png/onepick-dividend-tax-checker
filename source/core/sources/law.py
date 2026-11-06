"""국가법령정보센터 Open API 법령 원문 수집과 결측 보완.

화면(law.go.kr)에는 보이는데 코드에서 비는 흔한 원인과 대응:
- 항·호·목이 하나뿐이면 목록이 아니라 값 하나(dict)로 옴 → _as_list로 늘 목록으로 다룸
- 항내용이 글자가 아니라 [[글자, ...]] 같은 중첩 목록으로 옴 → _text로 펼침
- '제104조의27'의 '의27'은 조문가지번호 칸에 따로 있음 → 번호와 가지번호를 함께 비교
- 장·절 제목 행(조문여부 '전문')이 조문처럼 섞임 → 조문여부가 '조문'인 행만 봄
- 검색 결과가 하나면 목록이 아니라 dict로 옴, 비슷한 이름(시행령·시행규칙)이 섞임 → 이름이 정확히 같은 현행 법령만
- 인증값(OC) 오류·점검이면 JSON이 아닌 HTML이 옴 → '조회 실패'로 기록하고 data/processed/law/articles.json 보관본으로 대체

법령 원문은 그대로 보여 주고 요약·생성하지 않는다(RAG는 검색만).
"""
import json
import re
from pathlib import Path

import pandas as pd

from core.sources.base import API_ERROR, NO_DATA, OK, STORED, UNVERIFIED, Client, Fetched, Source, secret

BASE = "https://www.law.go.kr/DRF"
KEY_NAME = "LAW_OC"
# 보관본은 core.law_search가 만든 파일 하나뿐이다(원문의 기준). 실행 폴더와 상관없이 같은 파일을 본다.
STORED_PATH = Path(__file__).resolve().parents[3] / "data" / "processed" / "law" / "articles.json"


def _as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _text(value) -> str:
    """중첩 목록이어도 글자만 이어 붙인다."""
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join(t for t in (_text(v) for v in value) if t)
    return str(value).strip()


def parse_article_label(label) -> tuple[str, str]:
    """'제104조의27' · '104의27' · 104 → ('104', '27') / ('104', '')."""
    m = re.search(r"(\d+)\s*조?\s*(?:의\s*(\d+))?", str(label))
    if not m:
        raise ValueError(f"조문 번호로 볼 수 없음: {label!r}")
    return m.group(1), m.group(2) or ""


def flatten_article(unit: dict) -> dict:
    """조문단위 하나 → {'title', 'text', 'paragraphs': [{'paragraph', 'text'}]}. 항 아래 호·목을 들여 붙인다."""
    paragraphs = []
    for p in _as_list(unit.get("항")):
        if not isinstance(p, dict):
            continue
        lines = [_text(p.get("항내용"))]
        for h in _as_list(p.get("호")):
            if isinstance(h, dict):
                lines.append(_text(h.get("호내용")))
                lines += [_text(m.get("목내용")) for m in _as_list(h.get("목")) if isinstance(m, dict)]
        paragraphs.append({"paragraph": _text(p.get("항번호")), "text": "\n".join(x for x in lines if x)})
    head = _text(unit.get("조문내용"))
    body = "\n".join(p["text"] for p in paragraphs)
    return {"title": _text(unit.get("조문제목")), "text": "\n".join(x for x in (head, body) if x), "paragraphs": paragraphs}


def find_article_unit(law_body: dict, number, branch="") -> dict | None:
    units = _as_list(law_body.get("법령", {}).get("조문", {}).get("조문단위"))
    for u in units:
        if not isinstance(u, dict) or _text(u.get("조문여부")) not in ("조문", ""):
            continue
        same_branch = _text(u.get("조문가지번호")).lstrip("0") == str(branch or "").lstrip("0")
        if _text(u.get("조문번호")) == str(number) and same_branch:
            return u
    return None


def stored_article(name: str, number, branch="", path: Path | str = STORED_PATH) -> Fetched:
    """미리 받아 둔 data/processed/law/articles.json에서 조문을 찾는다(API가 안 될 때)."""
    path = Path(path)
    if not path.exists():
        return Fetched(None, UNVERIFIED, Source("보관본", {"path": str(path)}), [f"보관본 없음: {path}"])
    data = json.loads(path.read_text(encoding="utf-8"))
    want = (str(number), str(branch or ""))
    hits = []
    for passage in data.get("passages", []):
        if passage.get("law") != name:
            continue
        try:
            if parse_article_label(passage.get("article", "")) == want:
                hits.append(passage)
        except ValueError:
            continue
    if not hits:
        return Fetched(None, UNVERIFIED, Source("보관본", {"path": str(path)}), [f"보관본에 {name} 제{number}조 없음"])
    value = {
        "title": hits[0].get("article", ""),
        "text": "\n".join(h.get("text", "") for h in hits),
        "paragraphs": [{"paragraph": h.get("paragraph", ""), "text": h.get("text", "")} for h in hits],
    }
    note = f"{data.get('fetched', '')} 받아 둔 사본 · 시행 {hits[0].get('effective', '')} · 현행본과 다를 수 있음"
    return Fetched(value, STORED, Source("보관본", {"path": str(path)}, url=hits[0].get("url"), note=note),
                   [f"보관본 {len(hits)}개 항"])


class Law:
    """법령 원문 요청 묶음. oc를 주지 않으면 비밀 입력(base.secret, 이름 LAW_OC)으로 받는다."""

    def __init__(self, oc: str | None = None, client: Client | None = None, stored_path: Path | str = STORED_PATH):
        self._oc = oc
        self.client = client or Client()
        self.stored_path = stored_path

    @property
    def oc(self) -> str:
        if not self._oc:
            self._oc = secret(KEY_NAME, "국가법령정보센터 OC(인증값) 입력(화면에 보이지 않음): ")
        return self._oc

    def _json(self, endpoint: str, params: dict) -> dict | None:
        raw = self.client.get(f"{BASE}/{endpoint}", {"OC": self.oc, "type": "JSON", **params},
                              keep=lambda b: b.lstrip()[:1] == b"{")
        try:
            return json.loads(raw)
        except ValueError:
            return None  # 인증값 오류·점검 때 HTML이 옴

    def search(self, name: str) -> Fetched:
        """법령 이름이 정확히 같은 현행 법령 목록."""
        body = self._json("lawSearch.do", {"target": "law", "query": name})
        if body is None:
            return Fetched(None, API_ERROR, Source("lawSearch", {"query": name}), ["lawSearch: JSON이 아닌 응답(OC 확인)"])
        laws = _as_list(body.get("LawSearch", {}).get("law"))
        df = pd.DataFrame([x for x in laws if isinstance(x, dict)])
        if df.empty or "법령명한글" not in df:
            return Fetched(None, NO_DATA, Source("lawSearch", {"query": name}), ["lawSearch: 검색 결과 없음"])
        df = df[df["법령명한글"].map(lambda n: re.sub(r"\s", "", str(n)) == re.sub(r"\s", "", name))]
        if "현행연혁코드" in df:
            df = df[df["현행연혁코드"].isin(["현행", ""]) | df["현행연혁코드"].isna()]
        status = OK if not df.empty else NO_DATA
        return Fetched(df.reset_index(drop=True), status, Source("lawSearch", {"query": name}), [f"lawSearch: {len(df)}건"])

    def article(self, name: str, label) -> Fetched:
        """조문 원문. API → 실패하면 보관본. 예: law.article('조세특례제한법', '제104조의27')."""
        number, branch = parse_article_label(label)
        attempts: list[str] = []
        found = self.search(name)
        attempts += found.attempts
        if found.found:
            row = found.value.iloc[0]
            mst = str(row.get("법령일련번호", ""))
            body = self._json("lawService.do", {"target": "law", "MST": mst})
            if body is None:
                attempts.append("lawService: JSON이 아닌 응답")
            else:
                unit = find_article_unit(body, number, branch)
                if unit:
                    value = flatten_article(unit)
                    attempts.append(f"lawService: 제{number}조{'의' + branch if branch else ''} {len(value['paragraphs'])}개 항")
                    src = Source("lawService", {"MST": mst}, url=f"https://www.law.go.kr/법령/{name}",
                                 note=f"시행 {row.get('시행일자', '')}")
                    return Fetched(value, OK, src, attempts)
                attempts.append("lawService: 조문 없음")
        stored = stored_article(name, number, branch, self.stored_path)
        stored.attempts = attempts + stored.attempts
        return stored
