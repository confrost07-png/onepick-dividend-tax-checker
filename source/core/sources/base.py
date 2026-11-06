"""수집 공통 부품: 결측 상태, 숫자 변환, 재시도·원본 캐시, 출처 기록, 이어받기.

원칙: 값을 못 찾으면 0이나 추정값으로 채우지 않는다. 왜 없는지(상태)와 어디까지 찾아봤는지(시도 경로)를 남긴다.
"""
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd

OK = "정상"
NO_DATA = "데이터 없음"  # 원천이 '값 없음'이라고 응답함
API_ERROR = "조회 실패"  # 키·한도·점검·네트워크 문제. 데이터가 없다는 뜻이 아님
FROM_ORIGINAL = "원문에서 찾음"  # API에는 없고 공시 원문 표에서 찾음. 사람이 원문을 한 번 더 확인
STORED = "보관본 사용"  # API 대신 미리 저장해 둔 사본을 씀
UNVERIFIED = "확인 불가"  # 모든 경로를 시도했지만 값이 없거나 하나로 정해지지 않음

STATUSES = [OK, NO_DATA, API_ERROR, FROM_ORIGINAL, STORED, UNVERIFIED]

# 캐시 파일 이름·출처 기록에 남기지 않는 비밀 파라미터
SECRET_PARAMS = ("crtfc_key", "OC", "serviceKey")

DEFAULT_CACHE_DIR = Path("data/raw")  # .gitignore에 들어 있어 커밋되지 않음


@dataclass(frozen=True)
class Source:
    """값 하나의 출처. params에는 비밀값을 넣지 않는다."""

    api: str
    params: dict = field(default_factory=dict)
    rcept_no: str | None = None
    url: str | None = None
    note: str = ""


@dataclass
class Fetched:
    """수집 결과 하나. value가 None이면 status가 이유를 말한다.

    unit: value의 단위(원). 백만 원 단위 값이면 1_000_000. 원 단위로 바꾸려면 value × unit.
    attempts: 시도한 경로와 결과를 순서대로 적은 기록.
    """

    value: Any
    status: str
    source: Source | None = None
    attempts: list[str] = field(default_factory=list)
    unit: int = 1

    @property
    def found(self) -> bool:
        return self.value is not None and self.status in (OK, FROM_ORIGINAL, STORED)

    @property
    def won(self) -> int | float | None:
        """원 단위 값. 숫자가 아니면 None."""
        if isinstance(self.value, (int, float)) and not isinstance(self.value, bool):
            return self.value * self.unit
        return None


def public_params(params: dict) -> dict:
    return {k: v for k, v in params.items() if k not in SECRET_PARAMS}


# --- 비밀키 입력 ---

_SECRETS: dict[str, str] = {}  # 이번 실행 동안만 메모리에 둔다. 파일에 쓰지 않는다.


def _colab_secret(name: str) -> str | None:
    try:
        from google.colab import userdata  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        return userdata.get(name)
    except Exception:  # noqa: BLE001 - 보안 비밀이 없거나 접근 허용 전
        return None


def secret(name: str, prompt: str | None = None, ask: Callable[[str], str] | None = None) -> str:
    """API 키를 화면에 보이지 않게 받는다.

    순서: 이번 실행에서 이미 받은 값 → 환경변수 name → Colab 보안 비밀 name → 숨김 입력(getpass).
    받은 키는 메모리에만 두며 출력·캐시 파일·출처 기록에 남기지 않는다.
    """
    import os

    if name in _SECRETS:
        return _SECRETS[name]
    value = os.environ.get(name) or _colab_secret(name)
    if not value:
        if ask is None:
            from getpass import getpass as ask
        value = ask(prompt or f"{name} 입력(화면에 보이지 않음): ")
    value = (value or "").strip()
    if not value:
        raise ValueError(f"{name}가 비어 있습니다.")
    _SECRETS[name] = value
    return value


def forget_secret(name: str) -> None:
    """잘못 입력한 키를 지워 다음 secret() 호출에서 다시 묻게 한다."""
    _SECRETS.pop(name, None)


# --- 숫자·이름 정리 ---

_EMPTY = {"", "-", "−", "–", "N/A", "NA", "nan", "None", "해당없음", "해당사항없음"}


def to_number(raw) -> int | float | None:
    """공시 숫자 문자열 → int 또는 float. 비어 있거나 '-'이면 None (0으로 바꾸지 않는다).

    '1,234' → 1234 · '△1,234'·'(1,234)'·'-1,234' → -1234 · '12.5' → 12.5 · '12.5%' → 12.5
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return None if raw != raw else raw  # NaN은 None
    s = re.sub(r"\s", "", str(raw)).replace(",", "").rstrip("%")
    if s in _EMPTY:
        return None
    negative = False
    if s[0] in "△▲":
        negative, s = True, s[1:]
    elif s.startswith("(") and s.endswith(")"):
        negative, s = True, s[1:-1]
    if s[:1] in ("-", "−"):
        negative, s = not negative, s[1:]
    try:
        value = float(s) if "." in s else int(s)
    except ValueError:
        return None
    return -value if negative else value


def squash(text: str) -> str:
    """비교용 이름: 공백과 가운뎃점을 모두 지운다. '현금ㆍ현물 배당결정' → '현금현물배당결정'."""
    return re.sub(r"[\sㆍ·•‧]", "", str(text or ""))


def strip_brackets(text: str) -> str:
    """비교용 이름에서 괄호 덧말과 앞 번호를 지운다. 'Ⅰ. 당기순이익(손실)' → '당기순이익'."""
    s = re.sub(r"\([^)]*\)|\[[^\]]*\]", "", squash(text))
    return re.sub(r"^([0-9]+|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+|[가-하])\.", "", s)


_UNITS = {"백만원": 1_000_000, "천원": 1_000, "억원": 100_000_000, "원": 1}


def unit_from_label(label: str) -> int:
    """항목 이름 괄호 속 단위 → 원 단위 배수. '현금배당금총액(백만원)' → 1_000_000. 없으면 1."""
    for inner in re.findall(r"\(([^)]*)\)", squash(label)):
        if inner in _UNITS:
            return _UNITS[inner]
    return 1


# --- 재시도와 원본 캐시 ---

Fetch = Callable[[str, dict], bytes]


class FetchError(Exception):
    """재시도해도 응답을 받지 못함."""


def http_fetch(url: str, params: dict, timeout: float = 20) -> bytes:
    import requests

    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    return response.content


def scrub(text: str) -> str:
    """오류 메시지 속 URL에 섞인 키를 가린다. 'crtfc_key=abc&' → 'crtfc_key=***&'."""
    return re.sub(rf"({'|'.join(SECRET_PARAMS)})=[^&\s'\"]+", r"\1=***", str(text))


def _is_client_error(error: Exception) -> bool:
    status = getattr(getattr(error, "response", None), "status_code", None)
    return status is not None and 400 <= status < 500


class Client:
    """재시도와 원본 캐시를 붙인 GET.

    - 네트워크 오류·5xx는 backoff × 2^n초 쉬고 다시 시도한다. 4xx는 다시 시도하지 않는다.
    - cache_dir가 있으면 응답 원본을 저장해 두고 다음에는 저장본을 쓴다(호출 한도 절약, 결측 원인 다시 보기).
      keep(응답)이 False면 저장하지 않는다(한도 초과·점검 응답처럼 다시 받아야 하는 경우).
    - 이번 실행 동안은 remember(응답)가 True인 응답을 메모리에 기억해 같은 요청을 다시 보내지 않는다.
      remember를 주지 않으면 keep을 따른다('데이터 없음'처럼 파일로는 남기지 않지만 같은 실행에서는 다시 물을 필요 없는 응답).
    - fetch를 바꿔 끼우면 인터넷 없이 테스트할 수 있다.
    """

    def __init__(
        self,
        fetch: Fetch | None = None,
        cache_dir: Path | str | None = None,
        retries: int = 3,
        backoff: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.fetch = fetch or http_fetch
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.retries = retries
        self.backoff = backoff
        self.sleep = sleep
        self.calls = 0  # 실제로 원천에 보낸 요청 수
        self._memo: dict[str, bytes] = {}

    @staticmethod
    def _key(url: str, params: dict) -> str:
        return json.dumps([url, sorted(public_params(params).items())], ensure_ascii=False, default=str)

    def cache_path(self, url: str, params: dict) -> Path | None:
        if not self.cache_dir:
            return None
        digest = hashlib.sha256(self._key(url, params).encode()).hexdigest()[:20]
        folder = re.sub(r"[^0-9A-Za-z]+", "_", url.split("://")[-1]).strip("_")
        return self.cache_dir / folder / f"{digest}.bin"

    def get(self, url: str, params: dict, *, keep: Callable[[bytes], bool] | None = None,
            remember: Callable[[bytes], bool] | None = None) -> bytes:
        key = self._key(url, params)
        if key in self._memo:
            return self._memo[key]
        path = self.cache_path(url, params)
        if path and path.exists():
            return path.read_bytes()
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                self.calls += 1
                data = self.fetch(url, params)
                break
            except Exception as error:  # noqa: BLE001 - 원천마다 예외 종류가 달라 모두 받는다
                last_error = error
                if _is_client_error(error) or attempt == self.retries - 1:
                    raise FetchError(scrub(f"{url} 요청 실패({attempt + 1}번 시도): {error}")) from None
                self.sleep(self.backoff * 2**attempt)
        else:  # retries가 0인 경우
            raise FetchError(scrub(f"{url} 요청 실패: {last_error}"))
        if path and (keep is None or keep(data)):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        remember = remember or keep
        if remember is None or remember(data):
            self._memo[key] = data
        return data

    def forget(self, url: str, params: dict) -> None:
        """저장본을 지워 다음에 원천에서 다시 받게 한다."""
        self._memo.pop(self._key(url, params), None)
        path = self.cache_path(url, params)
        if path and path.exists():
            path.unlink()


# --- 이어받기 (하루 호출 한도) ---


class LimitReached(Exception):
    """하루 호출 한도를 넘음. 다음 날 같은 체크포인트로 이어서 돌린다."""


def run_resumable(keys: Iterable, task: Callable[[Any], Any], checkpoint: Path | str) -> dict:
    """keys마다 task(key)를 부르고, 끝난 key를 checkpoint(JSON)에 적는다.

    LimitReached가 나면 멈추고 남은 key를 돌려준다. 다음에 같은 checkpoint로 부르면 끝난 key는 건너뛴다.
    결과 자체는 저장하지 않는다(응답 원본은 Client 캐시에 남으므로 다시 불러도 호출이 늘지 않는다).
    """
    checkpoint = Path(checkpoint)
    done: set[str] = set(json.loads(checkpoint.read_text())) if checkpoint.exists() else set()
    keys = list(keys)
    results: dict = {}
    stopped = False
    for key in keys:
        if str(key) in done:
            continue
        try:
            results[key] = task(key)
        except LimitReached:
            stopped = True
            break
        done.add(str(key))
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_text(json.dumps(sorted(done), ensure_ascii=False))
    return {
        "results": results,
        "remaining": [k for k in keys if str(k) not in done],
        "stopped_by_limit": stopped,
    }


# --- 수집 현황표 ---


def status_table(items: dict[str, Fetched]) -> pd.DataFrame:
    """항목 이름 → Fetched를 한 표로. 팀 수집 현황표·원문 확인 목록에 쓴다."""
    rows = []
    for name, f in items.items():
        rows.append({
            "항목": name,
            "값": f.value if not isinstance(f.value, pd.DataFrame) else f"표 {len(f.value)}행",
            "단위(원)": f.unit,
            "상태": f.status,
            "출처 API": f.source.api if f.source else None,
            "접수번호": f.source.rcept_no if f.source else None,
            "메모": f.source.note if f.source else "",
            "시도 경로": " → ".join(f.attempts),
        })
    # dtype=object: 정수 값이 결측 행 때문에 실수(4.8e+09)로 바뀌지 않게
    return pd.DataFrame(rows, columns=["항목", "값", "단위(원)", "상태", "출처 API", "접수번호", "메모", "시도 경로"], dtype=object)
