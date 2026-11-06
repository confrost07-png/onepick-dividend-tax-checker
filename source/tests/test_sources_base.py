"""수집 공통 부품: 숫자 변환, 단위, 비밀키, 재시도·캐시, 이어받기."""
import json

import pytest

from core.sources import base
from core.sources.base import Client, FetchError, LimitReached, run_resumable, scrub, to_number, unit_from_label


@pytest.mark.parametrize("raw, expected", [
    ("1,234", 1234), ("△1,234", -1234), ("(1,234)", -1234), ("-1,234", -1234),
    ("12.5", 12.5), ("12.5%", 12.5), (" 7 ", 7), (0, 0),
])
def test_to_number_reads_disclosure_formats(raw, expected):
    assert to_number(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "-", "−", "nan", float("nan"), "해당없음", "abc"])
def test_to_number_keeps_missing_as_none_not_zero(raw):
    assert to_number(raw) is None


def test_unit_from_label():
    assert unit_from_label("현금배당금총액(백만원)") == 1_000_000
    assert unit_from_label("주당 현금배당금(원)") == 1
    assert unit_from_label("(연결)현금배당성향(%)") == 1


def test_secret_uses_env_then_prompt_and_never_prints(monkeypatch):
    base._SECRETS.clear()
    monkeypatch.setenv("TEST_KEY", "from-env")
    assert base.secret("TEST_KEY", ask=lambda _: pytest.fail("물으면 안 됨")) == "from-env"
    base._SECRETS.clear()
    monkeypatch.delenv("TEST_KEY")
    assert base.secret("TEST_KEY", ask=lambda _: " typed ") == "typed"
    assert base.secret("TEST_KEY", ask=lambda _: pytest.fail("두 번 묻지 않음")) == "typed"
    base.forget_secret("TEST_KEY")
    with pytest.raises(ValueError):
        base.secret("TEST_KEY", ask=lambda _: "")


def test_scrub_hides_keys_in_error_text():
    text = "404 for url: https://x/api?crtfc_key=SECRET123&corp_code=1 OC=abc"
    assert "SECRET123" not in scrub(text) and "abc" not in scrub(text)


def test_client_retries_then_caches_without_key_in_path(tmp_path):
    calls = []

    def flaky(url, params):
        calls.append(params)
        if len(calls) < 2:
            raise ConnectionError("끊김")
        return b'{"status":"000"}'

    c = Client(fetch=flaky, cache_dir=tmp_path, sleep=lambda s: None)
    assert c.get("https://a/b.json", {"crtfc_key": "K1", "x": 1}) == b'{"status":"000"}'
    assert len(calls) == 2
    # 키가 달라도 같은 요청이면 저장본을 쓰고, 파일 이름에 키가 없다
    assert c.get("https://a/b.json", {"crtfc_key": "K2", "x": 1}) == b'{"status":"000"}'
    assert len(calls) == 2
    assert all("K1" not in str(p) for p in tmp_path.rglob("*"))


def test_client_does_not_cache_when_keep_says_no(tmp_path):
    c = Client(fetch=lambda u, p: b"limit", cache_dir=tmp_path)
    c.get("https://a/b", {}, keep=lambda b: False)
    assert not list(tmp_path.rglob("*.bin"))


def test_client_gives_up_and_hides_key():
    def down(url, params):
        raise ConnectionError(f"{url}?crtfc_key={params['crtfc_key']}")

    c = Client(fetch=down, retries=2, sleep=lambda s: None)
    with pytest.raises(FetchError) as e:
        c.get("https://a/b", {"crtfc_key": "TOPSECRET"})
    assert "TOPSECRET" not in str(e.value)


def test_run_resumable_stops_at_limit_and_continues(tmp_path):
    ck = tmp_path / "ck.json"
    budget = {"left": 2}

    def task(k):
        if budget["left"] == 0:
            raise LimitReached()
        budget["left"] -= 1
        return k * 10

    first = run_resumable([1, 2, 3, 4], task, ck)
    assert first["stopped_by_limit"] and first["remaining"] == [3, 4]
    assert json.loads(ck.read_text()) == ["1", "2"]
    budget["left"] = 5  # 다음 날
    second = run_resumable([1, 2, 3, 4], task, ck)
    assert second["results"] == {3: 30, 4: 40} and second["remaining"] == []
