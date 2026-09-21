"""Cross-platform smoke test of the web app: start the server, run one short scenario through
the HTTP API, check that the report was written. Used by the build workflow on every OS.
    python webapp/smoke.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request

PORT = 8097
BASE = f"http://127.0.0.1:{PORT}"


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=10) as r:
        return json.loads(r.read())


def post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def main() -> int:
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "webapp.server:app", "--host", "127.0.0.1", "--port", str(PORT)])
    try:
        for _ in range(60):
            try:
                if get("/api/health")["ok"]:
                    break
            except Exception:
                time.sleep(1)
        else:
            print("server did not start"); return 1
        j = post("/api/run", {"scenario": "clear_line", "overrides": {"duration_s": 3}, "speed": 0})
        rid = j["run_id"]
        for _ in range(120):
            st = get(f"/api/run/{rid}")
            if st.get("done"):
                break
            time.sleep(1)
        else:
            print("run did not finish"); return 1
        with urllib.request.urlopen(f"{BASE}/runs/{rid}/report", timeout=10) as r:
            pdf = r.read()
        if not pdf.startswith(b"%PDF"):
            print("report is not a PDF"); return 1
        print(f"web app ok: run {rid}, report {len(pdf)} bytes, state {st.get('summary', {}).get('final_state', '?')}")
        return 0
    finally:
        srv.terminate()
        try:
            srv.wait(10)
        except subprocess.TimeoutExpired:
            srv.kill()


if __name__ == "__main__":
    sys.exit(main())
