"""app/web/src/bank.ts의 함수(날짜·이미 찬 시간·모형 예약 번호)와 applications.ts(신청 내역)를 Python으로.
신청 내역은 웹이 브라우저(localStorage)에 남기듯, Streamlit은 이 세션(st.session_state)에만 남긴다."""
from __future__ import annotations

import random
import string
from datetime import date, datetime, timedelta

import streamlit as st

DAY = "일월화수목금토"


def day_name(d: date) -> str:
    return DAY[(d.weekday() + 1) % 7]


def date_text(d: date) -> str:
    return f"{d.month}월 {d.day}일({day_name(d)})"


def next_business_days(n: int, start: date | None = None) -> list[date]:
    d, out = start or date.today(), []
    while len(out) < n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            out.append(d)
    return out


def is_taken(branch: str, d: date, slot: str) -> bool:
    """bank.ts isTaken: 지점·날짜·시간으로 정해진 값(날마다 같은 결과). JS getMonth()는 0부터."""
    key = f"{branch}{d.month - 1}{d.day}{slot}"
    h = 0
    for ch in key:
        h = (h * 31 + ord(ch)) % 1000
    return h % 3 == 0


def mock_number() -> str:
    a = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"A-{a}-{random.randint(1000, 9999)}"


def list_apps(who: str) -> list[dict]:
    return st.session_state.setdefault("apps", {}).setdefault(who, [])


def add_app(who: str, app: dict) -> bool:
    st.session_state.setdefault("apps", {})[who] = [app, *list_apps(who)]
    return True


def cancel_app(who: str, no: str) -> list[dict]:
    now = datetime.now().isoformat()
    apps = [{**a, "status": "취소", "canceledAt": now} if a["no"] == no and a["status"] == "신청" else a for a in list_apps(who)]
    st.session_state["apps"][who] = apps
    return apps


def is_past(a: dict) -> bool:
    return date.fromisoformat(a["date"][:10]) < date.today()
