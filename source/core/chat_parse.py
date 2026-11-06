"""챗봇 입력 해석: 고객이 친 문장에서 값을 뽑고 검사한다.

기획안: 질문 순서와 칩은 코드로 고정하고, 자유 문장에서 값을 뽑는 데만 AI(서버 내 Ollama)를 쓴다.
먼저 규칙으로 뽑고, 규칙이 실패할 때만 llm 함수(core.llm_ollama, 이 컴퓨터의 Ollama)를 부른다.
어느 쪽으로 뽑든 같은 검사(validate_*)를 거친 값만 계산에 쓴다.
"""
import difflib
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable

UNKNOWN = "모름"
NONE_WORDS = ("없음", "없어", "없습니다", "없다", "안 받")
UNKNOWN_WORDS = ("모름", "몰라", "모르", "잘 모")

_HAS_NUMBER = re.compile(r"\d|[일이삼사오육칠팔구십백천]\s*[십백천만억원]")  # 숫자, 또는 '오십'·'천만'·'삼백'처럼 수를 이루는 말
MAX_AMOUNT = 1_000_000_000_000  # 1조 원: 이보다 크면 입력 실수로 본다
MAX_SHARES = 1_000_000_000

_UNITS = {"조": 10**12, "억": 10**8, "천만": 10**7, "백만": 10**6, "만": 10**4, "천": 10**3, "백": 10**2}
_AMOUNT_TOKEN = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(조|억|천만|백만|만|천|백)?")


@dataclass
class ParseResult:
    value: object = None  # int, list[Holding], UNKNOWN
    ok: bool = False
    error: str = ""
    by: str = "규칙"  # "규칙" / "AI"
    code: str = ""  # 실패 종류. "not_found" = 조회 대상 638곳에 없는 회사, "missing_shares" = 주식 수를 빠뜨린 회사,
    # "bad_shares" = 0 이하·소수 주식 수, "preferred" = 우선주
    excluded: list = field(default_factory=list)  # skip_outside일 때 목록에 없어 뺀 종목 [(적은 이름, 비슷한 대상 기업들)]


@dataclass(frozen=True)
class Holding:
    company: str
    shares: int


def parse_amount(text: str) -> ParseResult:
    """'500만 원', '1억 2천', '5,000,000원', '1.5억', '없음', '모름' → 원 단위 정수."""
    t = text.strip()
    if any(w in t for w in UNKNOWN_WORDS):
        return ParseResult(UNKNOWN, True)
    if any(w in t for w in NONE_WORDS):
        return ParseResult(0, True)

    if re.search(r"(?:^|\s)(?:-|−|마이너스)\s*\d", t):
        return ParseResult(error="금액은 0원 이상이어야 해요")
    t = _korean_amount(t)
    tokens = [(m.group(1), m.group(2)) for m in _AMOUNT_TOKEN.finditer(t)]
    if not tokens:
        return ParseResult(error="금액을 찾지 못했어요")
    # 말하는 순서대로 묶는다: '5천5백만' = (5천 + 5백) × 만, '2만5천' = 2만 + 5천
    total, small = Decimal(0), Decimal(0)
    big, small_units_only = None, True
    for num, unit in tokens:
        n = Decimal(num.replace(",", ""))
        if unit in ("조", "억"):
            total += (small + n) * _UNITS[unit]
            small, big, small_units_only = Decimal(0), unit, True
        elif unit in ("만", "천만", "백만"):
            total += (small + n * _UNITS[unit] // _UNITS["만"]) * _UNITS["만"]
            small, big, small_units_only = Decimal(0), "만", True
        else:
            small += n * _UNITS.get(unit, 1)
            small_units_only = small_units_only and unit in ("천", "백")
    # '1억 2천'처럼 억 뒤의 천·백은 천만·백만으로 읽는다(말할 때 '만'을 생략함)
    if small and big == "억" and small_units_only:
        small *= _UNITS["만"]
    return validate_amount(int(total + small))


_KOREAN_AMOUNT = re.compile(r"(?:(?<=[조억만])|(?<![가-힣\d,.]))(\d[\d,.]*\s*)?([일이삼사오육칠팔구]*[십백천만][일이삼사오육칠팔구십백천만]*)(?=\s*(?:원|억|조|$|[\s,.]))")


def _korean_amount(t: str) -> str:
    """'삼십만원' → '300000원', '3십만' → '30만', '1억 오천만' → '1억 50000000'. 규칙으로 읽어 AI가 자릿수를 틀리지 않게."""
    t = re.sub(r"(\d)\s*십", lambda m: f"{m.group(1)}0", t)
    # '30만'처럼 숫자 뒤의 단위는 그대로 둔다(아래 _AMOUNT_TOKEN이 읽음)
    return _KOREAN_AMOUNT.sub(lambda m: m.group(0) if m.group(1) else str(korean_number(m.group(2)) or m.group(2)), t)


def validate_amount(value) -> ParseResult:
    if value == UNKNOWN:
        return ParseResult(UNKNOWN, True)
    if not isinstance(value, int) or isinstance(value, bool):
        return ParseResult(error="금액은 원 단위 정수여야 해요")
    if value < 0:
        return ParseResult(error="금액은 0원 이상이어야 해요")
    if value > MAX_AMOUNT:
        return ParseResult(error="금액이 너무 커요. 단위를 확인해 주세요")
    return ParseResult(value, True)


# --- 회사 이름 맞추기 ---------------------------------------------------------------
# 영문자는 한글 읽기로 바꿔 비교한다: 'LG전자'와 '엘지전자', 'KT&G'와 '케이티앤지', 'C사'와 '씨사'가 같은 열쇠.
_LATIN_READ = {
    "A": "에이", "B": "비", "C": "씨", "D": "디", "E": "이", "F": "에프", "G": "지", "H": "에이치", "I": "아이",
    "J": "제이", "K": "케이", "L": "엘", "M": "엠", "N": "엔", "O": "오", "P": "피", "Q": "큐", "R": "알",
    "S": "에스", "T": "티", "U": "유", "V": "브이", "W": "더블유", "X": "엑스", "Y": "와이", "Z": "지", "&": "앤",
}
_QUOTES = "'\"‘’“”`「」『』〈〉《》<>[]"  # 이름을 감싼 따옴표·꺾쇠. 조회 대상 회사 이름에는 없는 글자
_NAME_NOISE = re.compile(r"\(주\)|㈜|주식회사|[\s.,·/()\-" + re.escape(_QUOTES) + "]")
SUGGEST_CUTOFF = 0.6  # 비슷한 이름 안내 기준 (difflib 비율). 안내만 하고 자동으로 고르지 않는다


def company_key(name: str) -> str:
    """비교용 열쇠: 띄어쓰기·(주)·문장부호를 빼고, 영문자는 한글 읽기로."""
    s = _NAME_NOISE.sub("", name).upper()
    return "".join(_LATIN_READ.get(ch, ch) for ch in s)


_key_cache: dict[int, tuple[int, dict[str, set[str]]]] = {}


def _key_index(known: dict[str, str]) -> dict[str, set[str]]:
    cached = _key_cache.get(id(known))
    if cached and cached[0] == len(known):
        return cached[1]
    index: dict[str, set[str]] = {}
    for company in set(known.values()):
        index.setdefault(company_key(company), set()).add(company)
    _key_cache[id(known)] = (len(known), index)
    return index


def match_company(name: str, known: dict[str, str]) -> tuple[str | None, list[str]]:
    """입력 이름 → (표준 회사명 또는 None, 비슷한 이름 최대 3개).

    정확히 같거나(종목코드 포함) 열쇠가 하나의 회사와만 같을 때만 회사를 돌려준다.
    그 밖에는 None과 비슷한 이름 후보를 돌려준다 — 후보를 골라 주지는 않는다(엉뚱한 회사로 계산 방지).
    """
    name = name.strip()
    if name in known:
        return known[name], []
    index = _key_index(known)
    key = company_key(name)
    if len(index.get(key, ())) == 1:
        return next(iter(index[key])), []
    near = difflib.get_close_matches(key, list(index), n=3, cutoff=SUGGEST_CUTOFF)
    return None, sorted({c for k in near for c in index[k]})[:3]


_PREFERRED = re.compile(r"^(.+?)\s*우[A-Z]?(?:\(전환\))?$")  # 삼성전자우, 현대차2우B 등


def preferred_base(name: str, known: dict[str, str]) -> str | None:
    """우선주 이름이면 보통주 회사명. 계산할 수 있는 우선주(api.data.prefs)는 이름 색인에 있어 여기까지 오지 않는다."""
    m = _PREFERRED.match(name.strip())
    if not m:
        return None
    base = re.sub(r"\d$", "", m.group(1))  # '현대차2우B'의 2
    return match_company(base, known)[0]


NOT_FOUND = "KIND 고배당기업 목록(2026년, 조회 대상 638곳)에 없어요."
NOT_FOUND_RULE = "목록에 없는 회사의 배당은 이번 고배당 분리과세 대상이 아니에요."


def topic_josa(word: str) -> str:
    """'은'/'는'. 한글로 끝나지 않으면 '은(는)'."""
    last = word.strip()[-1:] if word.strip() else ""
    if "가" <= last <= "힣":
        return "은" if (ord(last) - 0xAC00) % 28 else "는"
    return "은(는)"


def object_josa(word: str) -> str:
    """'을'/'를'. 한글로 끝나지 않으면 '을(를)'."""
    last = word.strip()[-1:] if word.strip() else ""
    if "가" <= last <= "힣":
        return "을" if (ord(last) - 0xAC00) % 28 else "를"
    return "을(를)"


def not_found_message(name: str, suggestions: list[str]) -> str:
    msg = f"'{name}'{topic_josa(name)} {NOT_FOUND} {NOT_FOUND_RULE}"
    if suggestions:
        return msg + f" 이름이 비슷한 대상 기업: {', '.join(suggestions)}. 이 중 하나라면 정확한 이름으로, 아니라면 이 종목은 빼고 알려 주세요."
    return msg + " 이름을 다르게 적었다면 [조회 대상 기업 목록]에서 찾아 주세요."


# --- 한글 숫자 ---------------------------------------------------------------------
_SINO_DIGIT = {"일": 1, "이": 2, "삼": 3, "사": 4, "오": 5, "육": 6, "칠": 7, "팔": 8, "구": 9}
_SINO_UNIT = {"십": 10, "백": 100, "천": 1000}
_NATIVE_TENS = {"열": 10, "스물": 20, "스무": 20, "서른": 30, "마흔": 40, "쉰": 50}
_NATIVE_ONES = {"한": 1, "하나": 1, "두": 2, "둘": 2, "세": 3, "셋": 3, "네": 4, "넷": 4, "다섯": 5, "여섯": 6,
                "일곱": 7, "여덟": 8, "아홉": 9}
_SINO = "[일이삼사오육칠팔구십백천만]+"
_NATIVE = f"(?:{'|'.join(_NATIVE_TENS)})(?:{'|'.join(_NATIVE_ONES)})?|(?:{'|'.join(_NATIVE_ONES)})"
# 한글 숫자 + '주' (앞은 문장 처음이나 띄어쓰기/문장부호여야 회사 이름 속 글자를 숫자로 읽지 않는다)
_KOREAN_SHARES = re.compile(rf"(?:(?<=^)|(?<=[\s,·/]))({_SINO}|{_NATIVE})\s*(?=주)")


def korean_number(word: str) -> int | None:
    """'삼백' 300, '이천오백' 2500, '백오십' 150, '열다섯' 15, '스무' 20 → 정수. 못 읽으면 None."""
    for tens, tv in _NATIVE_TENS.items():
        if word.startswith(tens):
            rest = word[len(tens):]
            return tv + (_NATIVE_ONES[rest] if rest else 0) if (not rest or rest in _NATIVE_ONES) else None
    if word in _NATIVE_ONES:
        return _NATIVE_ONES[word]
    total = section = num = 0
    for ch in word:
        if ch in _SINO_DIGIT:
            if num:
                return None  # '삼사'처럼 숫자만 이어지면 읽지 않는다
            num = _SINO_DIGIT[ch]
        elif ch in _SINO_UNIT:
            section += (num or 1) * _SINO_UNIT[ch]
            num = 0
        elif ch == "만":
            total += (section + num or 1) * 10_000
            section = num = 0
        else:
            return None
    return total + section + num or None


# --- 보유 종목 문장 ----------------------------------------------------------------
_FILLER = re.compile(r"주식\s*(?:을|를|은|는|이|가|도)?|(?:(?<=^)|(?<=\s))(?:한|약|대략|대충|대강|얼추|거의|총)(?=\s+\d)")
_SHARES = re.compile(r"(\d[\d,]*)\s*주")
_JOINERS = {"하고", "이랑", "랑", "그리고", "및", "와", "과", "또", "있고"}  # 앞 종목 뒤에 따로 쓴 연결어 낱말
_LEAD_PUNCT = re.compile(r"^[,·/]+")


_PARTICLE = re.compile(r"(?:을|를|은|는|이|가|도)$")


def _with_particle_dropped(cand: str) -> list[str]:
    """'삼성전기를' → ['삼성전기를', '삼성전기']. 이름 그대로를 먼저 맞춰 보고, 안 맞으면 조사를 뗀다."""
    bare = _PARTICLE.sub("", cand)
    return [cand, bare] if bare and bare != cand else [cand]


def _unmatched_name(word: str, known: dict[str, str]) -> str:
    """목록에 없는 이름: '우리금융도'처럼 조사를 떼야 비슷한 회사가 나오면 뗀 이름을 쓴다 ('디와이'의 '이'는 그대로)."""
    bare = _PARTICLE.sub("", word)
    return bare if bare and bare != word and match_company(bare, known)[1] else word


# 숫자 + 만·천·백 + '주': '2만 주', '3천 주', '1만 5천 주', '1만5000주' (회사 이름 속 숫자는 앞이 숫자·쉼표·점이 아니어야)
_MIXED_SHARES = re.compile(r"(?<![\d,.])(\d[\d,]*\s*[만천백](?:\s*\d[\d,]*\s*[천백]?)*)\s*(?=주)")


def _mixed_number(s: str) -> int:
    """'2만' 20000, '1만 5천' 15000, '1만5000' 15000, '2천5백' 2500."""
    total = section = 0
    for num, unit in re.findall(r"(\d[\d,]*)\s*([만천백]?)", s):
        n = int(num.replace(",", ""))
        if unit == "만":
            total += (section + n) * 10_000
            section = 0
        else:
            section += n * {"천": 1000, "백": 100}.get(unit, 1)
    return total + section


def _normalize_holdings_text(text: str) -> str:
    t = text.translate({ord(c): " " for c in _QUOTES})  # "'삼성전자' 100주" → " 삼성전자  100주"
    t = re.sub(r"(?<=\S)\s*우선주", "우", t)  # '삼성전자 우선주' → '삼성전자우'
    t = _MIXED_SHARES.sub(lambda m: f"{_mixed_number(m.group(1))}", t)
    t = _FILLER.sub(" ", t)
    t = _KOREAN_SHARES.sub(lambda m: f"{korean_number(m.group(1))} " if korean_number(m.group(1)) else m.group(0), t)
    return _FILLER.sub(" ", t)  # 숫자로 바꾼 뒤 생긴 '한 300' 같은 군말을 한 번 더 뺀다


def mentions_shares(text: str) -> bool:
    """'삼성전자 100주', '삼백 주'처럼 주식 수를 적었는지. '국내 주식 300만 원'의 '주식'은 세지 않는다."""
    return bool(_SHARES.search(_normalize_holdings_text(text)))


_MINUS = ("-", "−", "마이너스")


def ask_shares_again(company: str) -> str:
    """0주·음수처럼 가질 수 없는 주식 수를 받았을 때 되묻는 말."""
    return f"주식 수는 1주 이상이어야 해요. {company}{object_josa(company)} 몇 주 가지고 계신가요? (예: {company} 10주)"


def parse_holdings(text: str, known: dict[str, str], skip_outside: bool = False) -> ParseResult:
    """'C사 300주 · E사 120주', '삼성전자 주식 삼백 주쯤' → [Holding]. known은 {입력에 쓰일 이름: 표준 회사명}.

    주식 수 앞부분(앞 종목 다음부터)을 이름 후보로 보고, 긴 것부터 줄여 가며 회사 목록과 맞춘다
    ('KB금융 100주랑 신한지주 50주'의 '랑 신한지주' → '신한지주', 'LG 전자' → 'LG전자').
    """
    t = _normalize_holdings_text(text)
    if re.search(r"\d\.\d+\s*주", t):
        return ParseResult(error="주식 수는 1주 단위로 알려 주세요 (예: 삼성전자 10주)", code="bad_shares")
    pairs, start = [], 0
    for m in _SHARES.finditer(t):
        before = t[start:m.start()].rstrip()
        negative = before.endswith(_MINUS)
        if negative:
            before = before.removesuffix("마이너스").rstrip("-−").rstrip()
        words = [w for w in (_LEAD_PUNCT.sub("", w) for w in before.split()) if w and w not in _JOINERS]
        start = m.end()
        if not words:
            if negative:
                return ParseResult(error="주식 수는 1주 이상으로 알려 주세요 (예: 삼성전자 10주)", code="bad_shares")
            return ParseResult(error="종목과 주식 수를 찾지 못했어요 (예: C사 300주)")
        found = next(((i, c) for i in range(len(words)) for c in _with_particle_dropped(" ".join(words[i:]))
                      if match_company(c, known)[0]), None)
        name = found[1] if found else _unmatched_name(words[-1], known)
        if negative:
            # '삼성전자 -10주': 판 주식이나 오타일 수 있어 짐작하지 않고, 어느 회사인지 확인한 뒤 가진 주식 수를 다시 묻는다
            company, suggestions = match_company(name, known)
            if company is None:
                return ParseResult(error=not_found_message(name.strip(), suggestions), code="not_found")
            return ParseResult(error=ask_shares_again(company), code="bad_shares")
        # 'C사, E사 100주'처럼 주식 수 없이 적은 회사가 앞에 남으면 조용히 빼지 않고 수를 묻는다
        missing = _company_without_shares(words[:found[0]] if found else [], known)
        if missing:
            return ParseResult(error=f"{missing} 주식 수도 함께 알려 주세요 (예: {missing} 100주)", code="missing_shares")
        pairs.append((name, int(m.group(1).replace(",", ""))))
    if not pairs:
        # '삼성전자'처럼 회사 이름만 적었으면 AI가 수를 짐작하지 않도록 바로 수를 묻는다
        missing = _company_without_shares(t.split(), known)
        if missing:
            return ParseResult(error=f"{missing} 주식 수도 함께 알려 주세요 (예: {missing} 100주)", code="missing_shares")
        return ParseResult(error="종목과 주식 수를 찾지 못했어요 (예: C사 300주)")
    missing = _company_without_shares(t[start:].split(), known)  # 마지막 'N주' 뒤에 적은 회사
    if missing:
        return ParseResult(error=f"{missing} 주식 수도 함께 알려 주세요 (예: {missing} 100주)", code="missing_shares")
    return validate_holdings(pairs, known, skip_outside)


def _company_without_shares(words: list[str], known: dict[str, str]) -> str | None:
    """주식 수 없이 남은 낱말 중 회사 이름이 있으면 그 회사명."""
    words = [w for w in (_LEAD_PUNCT.sub("", w).rstrip(",·/") for w in words) if w and w not in _JOINERS]
    for i in range(len(words)):
        for j in range(len(words), i, -1):
            for c in _with_particle_dropped(" ".join(words[i:j])):
                company = match_company(c, known)[0]
                if company:
                    return company
    return None


def validate_holdings(pairs: list[tuple[str, int]], known: dict[str, str], skip_outside: bool = False) -> ParseResult:
    """skip_outside: 조회 대상 638곳에 없는 종목은 막지 않고 빼 두고(excluded) 나머지로 읽는다(① 보유 종목)."""
    holdings: dict[str, int] = {}
    excluded: list[tuple[str, list[str]]] = []
    for name, shares in pairs:
        company, suggestions = match_company(str(name), known)
        if company is None:
            base = preferred_base(str(name), known)
            if base is not None:
                # 계산할 수 있는 우선주는 known에 있어 위에서 이미 찾는다. 여기 오는 건 종목별 주당배당금을 확인하지 못한 우선주
                return ParseResult(error=f"{str(name).strip()}{topic_josa(str(name).strip())} {base}의 우선주예요. 이 우선주는 주당배당금을 "
                                         f"종목별로 확인하지 못해 아직 계산하지 않아요. 보통주({base})로 알려 주세요.", code="preferred")
            if skip_outside:
                excluded.append((str(name).strip(), suggestions))
                continue
            return ParseResult(error=not_found_message(str(name).strip(), suggestions), code="not_found")
        if shares is None:
            return ParseResult(error=f"{company} 주식 수도 함께 알려 주세요 (예: {company} 100주)", code="missing_shares")
        if isinstance(shares, int) and not isinstance(shares, bool) and shares <= 0:
            return ParseResult(error=ask_shares_again(company), code="bad_shares")
        if not isinstance(shares, int) or isinstance(shares, bool) or shares > MAX_SHARES:
            return ParseResult(error=f"{company} 주식 수를 확인해 주세요 (예: {company} 10주)", code="bad_shares")
        holdings[company] = holdings.get(company, 0) + shares
    return ParseResult([Holding(c, s) for c, s in holdings.items()], True, excluded=excluded)


@dataclass
class Parser:
    """규칙으로 먼저 해석하고, 실패하면 llm(text, kind) → dict를 불러 같은 검사를 거친다.

    llm은 서버 안 Ollama를 부르는 함수(core.llm_ollama.get_llm)를 넣는 자리다(꺼져 있으면 None). 반환 예:
      kind="holdings" → {"holdings": [{"company": "C사", "shares": 300}]}
      kind="amount"   → {"amount": 5000000} 또는 {"amount": "모름"}
    """

    known_companies: dict[str, str]
    llm: Callable[[str, str], dict] | None = None
    log: list[str] = field(default_factory=list)  # 입력값은 남기지 않고 해석 방식만 남긴다

    def amount(self, text: str) -> ParseResult:
        r = parse_amount(text)
        if r.ok or self.llm is None:
            self.log.append(f"amount:{r.by}:{r.ok}")
            return r
        out = self.llm(text, "amount") or {}
        r = validate_amount(out.get("amount"))
        # 숫자나 수를 나타내는 말('오십', '천만')이 없는 문장이면 AI가 읽은 값(금액·0원)을 받지 않는다.
        # '모름'·'없음'은 규칙이 먼저 읽으므로 AI의 '모름'도 받지 않는다
        # ('그만'·'처음부터'를 AI가 모름으로 읽어 다음 질문으로 넘어가던 것 막음. '그만'의 '만'은 금액 단위가 아님)
        if r.ok and (r.value == UNKNOWN or not _HAS_NUMBER.search(text)):
            r = ParseResult(error="입력하신 문장에서 금액을 확인하지 못했어요")
        r.by = "AI"
        self.log.append(f"amount:AI:{r.ok}")
        return r

    def _name_only(self, text: str) -> ParseResult:
        """종목도 주식 수도 못 읽은 짧은 말. 조회 대상 회사 이름과 비슷하면 '찾지 못함'과 비슷한 이름을 알려 준다
        ('sk하이닉스' → SK·SK가스 …). 비슷한 이름도 없으면 종목 입력이 아닌 말로 본다."""
        t = text.strip()
        if len(t) <= 20 and not re.search(r"[?？]|란$|뭐|무엇|어떻게", t):
            company, near = match_company(t, self.known_companies)
            if company:
                return ParseResult(error=f"{company} 주식 수도 함께 알려 주세요 (예: {company} 100주)", code="missing_shares")
            if near:
                return ParseResult(error=not_found_message(t, near), code="not_found")
        return ParseResult(error="종목을 찾지 못했어요")

    def holdings(self, text: str, skip_outside: bool = False) -> ParseResult:
        r = parse_holdings(text, self.known_companies, skip_outside)
        # 주식 수를 빠뜨렸거나(missing_shares) 수가 틀렸거나(bad_shares) 우선주(preferred)면 AI에 넘기지 않고 바로 안내한다
        # (AI가 수를 짐작하거나 '삼성전자우'를 '삼성전자'로 읽어 보통주로 계산하던 것 막음)
        if r.ok or self.llm is None or r.code in ("missing_shares", "bad_shares", "preferred"):
            self.log.append(f"holdings:{r.by}:{r.ok}")
            return r
        rule = r
        out = self.llm(text, "holdings") or {}
        pairs = [(h.get("company", ""), h.get("shares")) for h in out.get("holdings", [])]
        # AI가 문장에 없는 회사 이름을 만들어 내면(예: '삼성전기를' → '삼성전자') 받지 않는다
        written = company_key(text)
        invented = [str(n) for n, _ in pairs if not company_key(str(n)) or company_key(str(n)) not in written]
        if invented:
            r = ParseResult(error=f"'{invented[0]}'을(를) 입력하신 문장에서 확인하지 못했어요")
        elif any(str(n).strip().isdigit() for n, _ in pairs):
            r = ParseResult(error="종목 이름도 함께 알려 주세요 (예: 삼성전자 10주)")
        else:
            r = validate_holdings(pairs, self.known_companies, skip_outside) if pairs else self._name_only(text)
        # AI가 종목을 하나도 못 읽었으면, 규칙이 찾은 '목록에 없는 회사' 안내가 더 정확하다
        if not pairs and not r.ok and rule.code == "not_found" and r.code != "missing_shares":
            r = rule
        r.by = "AI"
        self.log.append(f"holdings:AI:{r.ok}")
        return r
