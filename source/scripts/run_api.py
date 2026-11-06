"""원픽 API 서버 실행. 접속 기록(access log)은 끈다: 고객 입력을 남기지 않기 위해서다.

사용: .venv/bin/python -m scripts.run_api [--port 8000]
"""
import argparse

import uvicorn

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    uvicorn.run("api.main:app", host="127.0.0.1", port=args.port, access_log=False)
