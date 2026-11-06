"""주식의 총수 현황(OpenDART stockTotqySttus): 발행주식총수·자기주식수·유통주식수 → raw.dart_share_total 행.

값은 받은 그대로 두고 숫자로만 읽는다. 쉼표·공백은 걷어 내고 '-'·빈칸은 비워 두며, (1,000)처럼 괄호로 적힌 숫자는 음수로 읽는다.
유통주식수가 비어 있고 발행·자기주식이 모두 있으면 발행 − 자기로 채우고 floating_note에 적는다. 0으로 채우지 않는다.
API 키는 환경변수 DART_API_KEY(또는 OPENDART_API_KEY), 없으면 .env 파일에서 읽는다. 키는 메모리에만 두고 화면·캐시 이름·DB에 남기지 않는다.
"""
import json
import os
import time
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = "https://opendart.fss.or.kr/api/stockTotqySttus.json"
CACHE = ROOT / "data" / "raw" / "dart_api_cache" / "stockTotqySttus"
ANNUAL = "11011"  # 사업보고서
NO_ROW = "(응답 없음)"  # 값이 없거나 오류인 응답도 1행 남겨 빠진 회사를 셀 수 있게 함
STOP_STATUS = {"010", "011", "012", "020", "021", "901"}  # 키 오류·한도 초과 등: 더 부르지 않고 멈춤

# 워크트리에는 .env가 없으므로 메인 폴더의 .env도 찾는다
ENV_FILES = [ROOT / ".env"] + ([ROOT.parents[2] / ".env"] if ROOT.parent.name == "worktrees" else [])


def number(v) -> Decimal | None:
    if v is None:
        return None
    s = str(v).replace(",", "").replace(" ", "").strip()
    if s in {"", "-", "−"}:
        return None
    neg = s.startswith("(") and s.endswith(")")
    try:
        n = Decimal(s.strip("()"))
    except InvalidOperation:
        return None
    return -n if neg else n


COMMON, PREF, TOTAL, NOTE, OTHER = "보통", "우선·종류", "합계", "비고", "기타"


def share_class(se: str | None) -> str:
    """회사마다 다르게 적는 주식 종류 이름(se)을 보통 / 우선·종류 / 합계 / 비고 / 기타로 묶는다. se 원문은 그대로 둔다.

    '의결권 없는 주식(우선주)'처럼 '없'·'우선'·'종류'·'상환'·'전환'이 있으면 우선·종류를 먼저 본다.
    '보통주 외'는 보통주가 아닌 주식이라 기타로 둔다.
    """
    s = "".join((se or "").split())
    if s == "비고":
        return NOTE
    if s == "합계":
        return TOTAL
    if any(w in s for w in ("우선", "종류", "상환", "전환", "의결권없", "의결권이없")):
        return PREF
    if s != "보통주외" and any(w in s for w in ("보통", "의결권있", "의결권이있")):
        return COMMON
    return OTHER


def rows_from_response(corp_code: str, bsns_year: int, reprt_code: str, payload: dict) -> list[dict]:
    base = {"corp_code": corp_code, "bsns_year": bsns_year, "reprt_code": reprt_code,
            "api_status": payload.get("status"), "api_message": payload.get("message")}
    items = payload.get("list") or []
    if payload.get("status") != "000" or not items:
        return [{**base, "se": NO_ROW, "share_class": None, "rcept_no": None, "stlm_dt": None, "issued": None, "treasury": None,
                 "floating": None, "issued_raw": None, "treasury_raw": None, "floating_raw": None, "floating_note": None}]
    out = []
    for it in items:
        issued, treasury, floating = number(it.get("istc_totqy")), number(it.get("tesstk_co")), number(it.get("distb_stock_co"))
        note = None
        if floating is None and issued is not None and treasury is not None:
            floating, note = issued - treasury, "유통주식수 칸이 비어 발행 − 자기로 계산"
        se = (it.get("se") or "").strip() or NO_ROW
        out.append({**base, "se": se, "share_class": share_class(se), "rcept_no": it.get("rcept_no"),
                    "stlm_dt": it.get("stlm_dt"), "issued": issued, "treasury": treasury, "floating": floating,
                    "issued_raw": it.get("istc_totqy"), "treasury_raw": it.get("tesstk_co"),
                    "floating_raw": it.get("distb_stock_co"), "floating_note": note})
    return out


KEY_NAMES = ("DART_API_KEY", "OPENDART_API_KEY")  # 앞의 이름을 먼저 찾음


def api_key(env_files: list[Path] = ENV_FILES) -> str | None:
    for name in KEY_NAMES:
        if os.environ.get(name):
            return os.environ[name]
    found = {}
    for path in env_files:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            name, sep, value = line.strip().partition("=")
            name = name.strip().removeprefix("export ").strip()
            if sep and name in KEY_NAMES and value.strip().strip("'\""):
                found.setdefault(name, value.strip().strip("'\""))
        for name in KEY_NAMES:
            if name in found:
                return found[name]
    return None


def cache_path(corp_code: str, bsns_year: int, reprt_code: str, cache: Path = CACHE) -> Path:
    return cache / f"{corp_code}_{bsns_year}_{reprt_code}.json"


RETRY_WAITS = (2, 30, 120)


def fetch(key: str, corp_code: str, bsns_year: int, reprt_code: str = ANNUAL, pause: float = 0.6,
          api: str = API, cache: Path = CACHE) -> dict:
    """한 회사 응답(JSON). 정상(000)·데이터 없음(013) 응답만 캐시에 두고 다시 받지 않는다. api·cache로 다른 OpenDART 표도 받는다."""
    path = cache_path(corp_code, bsns_year, reprt_code, cache)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    query = urllib.parse.urlencode({"crtfc_key": key, "corp_code": corp_code,
                                    "bsns_year": str(bsns_year), "reprt_code": reprt_code})
    for wait in RETRY_WAITS + (None,):
        try:
            with urllib.request.urlopen(f"{api}?{query}", timeout=60) as r:
                payload = json.loads(r.read().decode("utf-8"))
            break
        except (OSError, ValueError):
            if wait is None:
                raise RuntimeError(f"응답을 받지 못함: {corp_code}") from None  # 키가 든 주소는 오류에 남기지 않음
            time.sleep(wait)
    if payload.get("status") in {"000", "013"}:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    time.sleep(pause)
    return payload
