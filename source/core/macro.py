"""한국은행 ECOS 거시지표(경상수지·금리·환율·GDP·CPI·고용)를 받아 원문 그대로 표로 바꾼다.

API 키는 환경변수 ECOS_API_KEY, 없으면 .env(워크트리면 메인 폴더 .env)에서 읽는다. 키는 메모리에만 두고 화면·파일에 남기지 않는다.
값은 ECOS가 준 문자열을 숫자로만 바꾸고 다시 계산하지 않는다. 단위·통계표 이름은 응답에 있는 그대로 남긴다.
"""
import json
import os
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# 워크트리에는 data/raw·.env가 없으므로 메인 폴더 것을 쓴다
MAIN = ROOT.parents[2] if ROOT.parent.name == "worktrees" else ROOT
ENV_FILES = [ROOT / ".env"] + ([MAIN / ".env"] if MAIN != ROOT else [])
OUT_DIR = MAIN / "data" / "raw" / "macro"
API = "https://ecos.bok.or.kr/api"
KEY_NAME = "ECOS_API_KEY"
PAGE = 1000  # ECOS 한 번 호출 최대 행 수 안쪽
NO_DATA = "INFO-200"  # 해당 기간 자료 없음


@dataclass(frozen=True)
class Series:
    name: str        # 저장 파일 이름
    label: str       # 사람이 읽는 이름
    stat_code: str
    item_code: str
    cycle: str       # D·M·Q
    item_code2: str = "?"


# 데이터셋 기간: KRX 주가 2018-01-02 ~ 2026-10-20 (data/raw/krx/prices.csv), DART 배당 2017~2026 사업연도.
# 2017 사업연도의 전년 대비 변화를 만들 수 있게 2016년부터 받는다
SERIES = [
    Series("current_account_m", "경상수지", "301Y013", "000000", "M"),
    Series("base_rate_m", "한국은행 기준금리", "722Y001", "0101000", "M"),
    Series("ktb3y_d", "국고채(3년)", "817Y002", "010200000", "D"),
    Series("ktb3y_m", "국고채(3년)", "721Y001", "5020000", "M"),
    Series("usdkrw_d", "원/미국달러(매매기준율)", "731Y001", "0000001", "D"),
    Series("usdkrw_m", "원/미국달러(매매기준율) 월평균", "731Y004", "0000001", "M", "0000100"),
    Series("gdp_real_qoq_q", "실질 GDP 성장률(계절조정, 전기비)", "200Y102", "10111", "Q"),
    Series("gdp_real_yoy_q", "실질 GDP 성장률(원계열, 전년동기비)", "200Y102", "10211", "Q"),
    Series("gdp_real_level_q", "실질 GDP(계절조정, 연쇄가격)", "200Y104", "1400", "Q"),
    Series("cpi_m", "소비자물가지수 총지수", "901Y009", "0", "M"),
    Series("unemployment_rate_m", "실업률(계절조정)", "901Y027", "I61BC", "M", "I28B"),
    Series("employment_rate_m", "고용률(계절조정)", "901Y027", "I61E", "M", "I28B"),
]

PERIOD = {"D": ("20160101", "20261031"), "M": ("201601", "202610"), "Q": ("2016Q1", "2026Q4")}

COLUMNS = ["series", "label", "time", "value", "value_raw", "unit", "stat_code", "stat_name",
           "item_code1", "item_name1", "item_code2", "item_name2", "cycle"]


def api_key(env_files: list[Path] = ENV_FILES) -> str | None:
    if os.environ.get(KEY_NAME):
        return os.environ[KEY_NAME]
    for path in env_files:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            name, sep, value = line.strip().partition("=")
            name = name.strip().removeprefix("export ").strip()
            value = value.strip().strip("'\"")
            if sep and name == KEY_NAME and value:
                return value
    return None


def number(v) -> Decimal | None:
    s = str(v or "").replace(",", "").strip()
    if s in {"", "-"}:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def url(key: str, s: Series, start: int, end: int) -> str:
    begin, finish = PERIOD[s.cycle]
    parts = ["StatisticSearch", key, "json", "kr", str(start), str(end), s.stat_code, s.cycle, begin, finish,
             s.item_code, s.item_code2]
    return API + "/" + "/".join(urllib.parse.quote(p, safe="?") for p in parts)


def get_json(address: str, pause: float = 0.3) -> dict:
    with urllib.request.urlopen(address, timeout=30) as r:
        payload = json.load(r)
    time.sleep(pause)
    return payload


def fetch(key: str, s: Series, get=get_json) -> list[dict]:
    """한 지표의 전 기간 행을 PAGE씩 나눠 받는다. 오류 응답이면 키를 뺀 메시지로 멈춘다."""
    rows, start = [], 1
    while True:
        payload = get(url(key, s, start, start + PAGE - 1))
        if "StatisticSearch" not in payload:
            result = payload.get("RESULT", {})
            if result.get("CODE") == NO_DATA and rows:
                break
            raise RuntimeError(f"{s.name}: ECOS {result.get('CODE')} {result.get('MESSAGE')}")
        body = payload["StatisticSearch"]
        rows += body.get("row", [])
        if len(rows) >= int(body.get("list_total_count", 0)):
            break
        start += PAGE
    return [to_row(s, r) for r in rows]


def period_start(time: str, cycle: str) -> date:
    if cycle == "D":
        return date(int(time[:4]), int(time[4:6]), int(time[6:8]))
    if cycle == "M":
        return date(int(time[:4]), int(time[4:6]), 1)
    if cycle == "Q":
        return date(int(time[:4]), (int(time[5]) - 1) * 3 + 1, 1)
    raise ValueError(f"모르는 주기: {cycle}")


def db_rows(csv_rows: list[dict], source_file: str) -> list[dict]:
    """collect_macro가 저장한 CSV 행 → raw.ecos_macro 행. 빈 문자열은 NULL로 둔다."""
    out = []
    for r in csv_rows:
        out.append({
            "series": r["series"], "time": r["time"], "period_start": period_start(r["time"], r["cycle"]),
            "cycle": r["cycle"], "value": number(r["value_raw"]), "value_raw": r["value_raw"] or None,
            "unit": r["unit"] or None, "label": r["label"], "stat_code": r["stat_code"],
            "stat_name": r["stat_name"] or None, "item_code1": r["item_code1"], "item_name1": r["item_name1"] or None,
            "item_code2": r["item_code2"] or None, "item_name2": r["item_name2"] or None, "source_file": source_file,
        })
    return out


def to_row(s: Series, r: dict) -> dict:
    return {
        "series": s.name, "label": s.label, "time": r.get("TIME"),
        "value": number(r.get("DATA_VALUE")), "value_raw": r.get("DATA_VALUE"), "unit": r.get("UNIT_NAME"),
        "stat_code": r.get("STAT_CODE"), "stat_name": r.get("STAT_NAME"),
        "item_code1": r.get("ITEM_CODE1"), "item_name1": r.get("ITEM_NAME1"),
        "item_code2": r.get("ITEM_CODE2"), "item_name2": r.get("ITEM_NAME2"), "cycle": s.cycle,
    }
