"""시연판 API를 이 Mac에서 켜고 Tailscale Funnel로 인터넷에 연다 (웹 화면은 Vercel, report/실행안내/배포_안내.md).

Vercel(app/web/vercel.json)이 /api 요청을 이 Mac의 https://<Mac>.<tailnet>.ts.net 으로 넘기고,
여기서 FastAPI가 같은 Mac의 Ollama(localhost)와 PostgreSQL로 답을 만든다. 고객 입력을 바깥 AI로 보내지 않는다.

사용: uv run python -m scripts.serve_public [start|stop|status]
- start: DB·Ollama 확인 → API 켜기(127.0.0.1:8000, 접속 기록 끔) → Funnel 켜기 → 잠자기 막기
- stop: Funnel 끄기 → API 끄기
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from core import db
from core.law_search import EMBED_MODEL
from core.llm_ollama import MODEL, OLLAMA_URL

PORT = 8000
LOCAL = f"http://127.0.0.1:{PORT}"
ROOT = Path(__file__).resolve().parents[2]  # 저장소 맨 위
VERCEL_JSON = ROOT / "app" / "web" / "vercel.json"
TAILSCALE_APP = "/Applications/Tailscale.app/Contents/MacOS/Tailscale"


def tailscale(*args: str) -> subprocess.CompletedProcess:
    exe = shutil.which("tailscale") or TAILSCALE_APP
    if not Path(exe).exists():
        sys.exit("Tailscale이 없어요. tailscale.com에서 앱을 설치하고 로그인해 주세요.")
    return subprocess.run([exe, *args], capture_output=True, text=True)


def get(url: str, timeout: float = 3) -> bytes | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.read()
    except OSError:
        return None


def check_db() -> str:
    try:
        with db.connect() as conn:
            n = conn.execute("select count(*) from core.core_company").fetchone()[0]
        return f"PostgreSQL 연결됨 (회사 {n}곳)"
    except Exception as e:  # 연결 실패 이유를 그대로 보여 준다
        return f"PostgreSQL 연결 실패: {e}"


def check_ollama() -> str:
    raw = get(f"{OLLAMA_URL}/api/tags")
    if raw is None:
        return "Ollama 꺼짐: 채팅 값 읽기·사진 읽기가 안 되고, 검색은 글자 검색으로 바뀌어요 (켜기: ollama serve)"
    names = {m["name"].removesuffix(":latest") for m in json.loads(raw).get("models", [])}
    missing = [m for m in (MODEL, EMBED_MODEL) if m not in names]
    return f"Ollama 모델 없음: {', '.join(missing)} (ollama pull …)" if missing else f"Ollama 켜짐 ({MODEL}, {EMBED_MODEL})"


def public_host() -> str | None:
    out = tailscale("status", "--json")
    if out.returncode != 0:
        return None
    return json.loads(out.stdout).get("Self", {}).get("DNSName", "").rstrip(".") or None


def vercel_host() -> str:
    rules = json.loads(VERCEL_JSON.read_text(encoding="utf-8"))["rewrites"]
    api = next(r["destination"] for r in rules if r["source"].startswith("/api"))
    return api.split("/")[2]


def api_pids() -> list[int]:
    out = subprocess.run(["lsof", "-t", f"-iTCP:{PORT}", "-sTCP:LISTEN"], capture_output=True, text=True)
    return [int(p) for p in out.stdout.split()]


def start() -> None:
    print(check_db())
    print(check_ollama())
    if not api_pids():
        env = {**os.environ, "PYTHONPATH": str(ROOT / "source")}  # 계산 코드(source/)를 찾게
        subprocess.Popen([sys.executable, "-m", "scripts.run_api", "--port", str(PORT)], cwd=ROOT / "source", env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        for _ in range(60):  # 회사 638곳을 읽느라 몇 초 걸린다
            if get(f"{LOCAL}/api/health"):
                break
            time.sleep(1)
    if not get(f"{LOCAL}/api/health"):
        sys.exit(f"API가 켜지지 않았어요. 직접 실행해 오류를 보세요: uv run python -m scripts.run_api --port {PORT}")
    print(f"API 켜짐: {LOCAL}")

    out = tailscale("funnel", "--bg", str(PORT))
    if out.returncode != 0:
        sys.exit("Funnel을 켜지 못했어요. Tailscale 관리 화면에서 HTTPS와 Funnel을 켰는지 확인해 주세요.\n"
                 + (out.stderr or out.stdout).strip())
    host = public_host()
    print(f"인터넷 주소: https://{host}  (확인: https://{host}/api/health)")
    if host and host != vercel_host():
        print(f"주의: app/web/vercel.json의 API 주소({vercel_host()})가 이 주소와 달라요. 고친 뒤 Vercel에 다시 배포해 주세요.")

    # API가 켜져 있는 동안 Mac이 저절로 잠들지 않게 한다 (덮개를 닫으면 잠들 수 있음)
    subprocess.Popen(["caffeinate", "-i", "-w", str(api_pids()[0])], start_new_session=True)
    print("잠자기 막기 켜짐 (API가 꺼지면 함께 풀림)")


def stop() -> None:
    tailscale("funnel", "reset")
    print("Funnel 꺼짐")
    for pid in api_pids():
        subprocess.run(["kill", str(pid)])
    print("API 꺼짐")


def status() -> None:
    print(check_db())
    print(check_ollama())
    print(f"API: {'켜짐' if get(f'{LOCAL}/api/health') else '꺼짐'} ({LOCAL})")
    funnel = tailscale("funnel", "status")
    print("Funnel:", (funnel.stdout or funnel.stderr).strip() or "꺼짐")
    print(f"app/web/vercel.json API 주소: {vercel_host()}")


if __name__ == "__main__":
    {"start": start, "stop": stop, "status": status}.get((sys.argv[1:] or ["status"])[0], status)()
