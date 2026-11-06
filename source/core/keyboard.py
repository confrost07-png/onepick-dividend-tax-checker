"""한/영 전환을 잊고 친 글('tkatjdwjswk 10wn' → '삼성전자 10주')을 두벌식 자판 기준으로 한글로 되돌린다.

영문 낱말이 뜻이 있으면(조회 대상 회사 이름에 들어가는 KB·SK·POSCO, ETF·ISA 같은 금융 낱말) 그대로 두고,
나머지 영문 낱말을 한글 자판으로 옮겼을 때 모두 온전한 글자가 될 때만 바꾼다('samsung'처럼 글자가 안 되면 그대로).
"""
import re

# 두벌식 자판: 영문 자판 글쇠 → 자모
KEYMAP = {
    "q": "ㅂ", "w": "ㅈ", "e": "ㄷ", "r": "ㄱ", "t": "ㅅ", "y": "ㅛ", "u": "ㅕ", "i": "ㅑ", "o": "ㅐ", "p": "ㅔ",
    "a": "ㅁ", "s": "ㄴ", "d": "ㅇ", "f": "ㄹ", "g": "ㅎ", "h": "ㅗ", "j": "ㅓ", "k": "ㅏ", "l": "ㅣ",
    "z": "ㅋ", "x": "ㅌ", "c": "ㅊ", "v": "ㅍ", "b": "ㅠ", "n": "ㅜ", "m": "ㅡ",
    "Q": "ㅃ", "W": "ㅉ", "E": "ㄸ", "R": "ㄲ", "T": "ㅆ", "O": "ㅒ", "P": "ㅖ",
}
CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
JONG = ["", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ", "ㄻ", "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ", "ㅁ", "ㅂ", "ㅄ", "ㅅ",
        "ㅆ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"]
VOWEL_PAIR = {("ㅗ", "ㅏ"): "ㅘ", ("ㅗ", "ㅐ"): "ㅙ", ("ㅗ", "ㅣ"): "ㅚ", ("ㅜ", "ㅓ"): "ㅝ", ("ㅜ", "ㅔ"): "ㅞ",
              ("ㅜ", "ㅣ"): "ㅟ", ("ㅡ", "ㅣ"): "ㅢ"}
FINAL_PAIR = {("ㄱ", "ㅅ"): "ㄳ", ("ㄴ", "ㅈ"): "ㄵ", ("ㄴ", "ㅎ"): "ㄶ", ("ㄹ", "ㄱ"): "ㄺ", ("ㄹ", "ㅁ"): "ㄻ",
              ("ㄹ", "ㅂ"): "ㄼ", ("ㄹ", "ㅅ"): "ㄽ", ("ㄹ", "ㅌ"): "ㄾ", ("ㄹ", "ㅍ"): "ㄿ", ("ㄹ", "ㅎ"): "ㅀ", ("ㅂ", "ㅅ"): "ㅄ"}
SPLIT_FINAL = {v: k for k, v in FINAL_PAIR.items()}

# 뜻이 있어 바꾸지 않는 영문 낱말(소문자). 회사 이름에 들어가는 영문은 known_words로 더 받는다
MEANINGFUL = {"etf", "etn", "isa", "irp", "reits", "kospi", "kosdaq", "dps", "eps", "per", "pbr", "roe", "els", "dls",
              "ok", "no", "yes", "kind", "dart", "krx", "ai"}
_LATIN = re.compile(r"[A-Za-z]+")


def _syllable(cho: str, jung: str, jong: str = "") -> str:
    return chr(0xAC00 + (CHO.index(cho) * 21 + JUNG.index(jung)) * 28 + JONG.index(jong))


def compose(jamo: list[str]) -> str | None:
    """자모 줄을 글자로 묶는다. 초성+중성이 안 되는 자모가 남으면(온전한 글자가 아니면) None."""
    out, i, n = [], 0, len(jamo)
    while i < n:
        c = jamo[i]
        if c not in CHO or i + 1 >= n or jamo[i + 1] not in JUNG:
            return None
        v, i = jamo[i + 1], i + 2
        if i < n and (v, jamo[i]) in VOWEL_PAIR:
            v, i = VOWEL_PAIR[(v, jamo[i])], i + 1
        jong = ""
        # 받침: 다음 자모가 자음이고, 그 뒤가 모음이 아니면 받침으로 붙인다
        if i < n and jamo[i] in JONG and not (i + 1 < n and jamo[i + 1] in JUNG):
            jong, i = jamo[i], i + 1
            if i < n and (jong, jamo[i]) in FINAL_PAIR and not (i + 1 < n and jamo[i + 1] in JUNG):
                jong, i = FINAL_PAIR[(jong, jamo[i])], i + 1
        out.append(_syllable(c, v, jong))
    return "".join(out)


def to_hangul(word: str) -> str | None:
    """영문 낱말 하나를 두벌식 한글로. 온전한 글자가 안 되면 None."""
    jamo = [KEYMAP.get(ch) or KEYMAP.get(ch.lower()) for ch in word]
    if any(j is None for j in jamo):
        return None
    return compose(jamo)  # type: ignore[arg-type]


def fix_layout(text: str, known_words: set[str] = frozenset()) -> str | None:
    """한/영 전환을 잊은 영문 낱말을 한글로 바꾼 글. 바꿀 낱말이 없으면 None."""
    keep = MEANINGFUL | {w.lower() for w in known_words}
    changed = False

    def swap(m: re.Match) -> str:
        nonlocal changed
        w = m.group(0)
        if w.lower() in keep:
            return w
        h = to_hangul(w)
        if h is None:
            return w
        changed = True
        return h
    out = _LATIN.sub(swap, text)
    return out if changed else None


def latin_words(names) -> set[str]:
    """회사 이름들에 들어 있는 영문 낱말(KB, SK, POSCO …)."""
    return {w.lower() for n in names for w in _LATIN.findall(n)}
