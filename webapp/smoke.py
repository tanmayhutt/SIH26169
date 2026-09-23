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
        # a real-time run, with the disturbances changed while it is going
        j = post("/api/run", {"scenario": "clear_line", "overrides": {"duration_s": 5}, "speed": 1.0, "random_seed": False})
        rid = j["run_id"]
        time.sleep(2)
        d = post(f"/api/disturb/{rid}", {"disturbance": {"atmosphere": "fog", "jitter_px": 6}})
        if not d.get("queued"):
            print("live disturbance change refused:", d); return 1
        for _ in range(120):
            st = get(f"/api/run/{rid}")
            if st.get("done"):
                break
            time.sleep(1)
        else:
            print("run did not finish"); return 1
        segs = st.get("summary", {}).get("segments") or []
        if len(segs) < 2 or "fog" not in segs[1]["change"]:
            print("live disturbance change not in the summary:", segs); return 1
        with urllib.request.urlopen(f"{BASE}/runs/{rid}/scenario", timeout=10) as r:
            if b"atmosphere: fog" not in r.read():
                print("live disturbance change not saved in the scenario"); return 1
        with urllib.request.urlopen(f"{BASE}/runs/{rid}/report", timeout=10) as r:
            pdf = r.read()
        if not pdf.startswith(b"%PDF"):
            print("report is not a PDF"); return 1
        print(f"web app ok: run {rid}, report {len(pdf)} bytes, live change at {segs[1]['t_start_s']:.2f} s ({segs[1]['change'][:40]}...)")
        return 0
    finally:
        srv.terminate()
        try:
            srv.wait(10)
        except subprocess.TimeoutExpired:
            srv.kill()


if __name__ == "__main__":
    sys.exit(main())
