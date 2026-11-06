"""모든 테스트에 공통 설정: 실제 Ollama를 끄고, 이용 통계 숫자를 0에서 시작한다."""
import pytest

from core import llm_ollama, usage


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """테스트는 실제 Ollama를 부르지 않고, 이용 통계를 0에서 시작한다.

    AI가 필요한 테스트는 가짜 함수를 직접 넣는다.
    """
    monkeypatch.setenv("ONEPICK_OLLAMA", "0")
    llm_ollama.reset()
    usage.COUNTER.reset()
    yield
    llm_ollama.reset()
    usage.COUNTER.reset()
