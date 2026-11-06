"""이용 통계: 입력값 없이 점검 시작·완료·상담 연결 횟수만 센다.

기획안: "이용 통계: 입력값 없이 점검 시작·완료·상담 연결 횟수만 셈"
- 세는 것은 사건 이름과 횟수뿐이다. 종목·금액·문장 같은 입력값은 받지도 남기지도 않는다.
- 프로토타입은 서버 메모리에만 둔다(재시작하면 0). 실서비스는 A은행 기존 통계 체계를 따른다.
- 2026-11-03 기준 시연판 서버(source/api)에는 연결하지 않았다. 개인정보 안내에도 '시연판에서는 세지 않음'으로 적었다.
"""
import threading

START = "점검 시작"
COMPLETE = "점검 완료"
CONSULT = "상담 연결"
EVENTS = (START, COMPLETE, CONSULT)


class UsageCounter:
    def __init__(self):
        self._lock = threading.Lock()
        self._counts = {e: 0 for e in EVENTS}

    def record(self, event: str) -> None:
        if event not in EVENTS:
            raise ValueError(f"세지 않는 사건: {event}")
        with self._lock:
            self._counts[event] += 1

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counts)

    def reset(self) -> None:
        with self._lock:
            self._counts = {e: 0 for e in EVENTS}


COUNTER = UsageCounter()
