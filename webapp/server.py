"""Web application: the same Simulation as the desktop app, served to a browser.

    uvicorn webapp.server:app --host 127.0.0.1 --port 8095

Endpoints
    GET  /                         the app
    GET  /api/scenarios            names and contents of configs/scenarios/*.yaml
    POST /api/run                  start a run: {"scenario": name|null, "overrides": {...}, "video": upload id|null}
    POST /api/stop/{run_id}        stop early (the report is still written)
    WS   /ws/{run_id}              live frames (scene, camera) and per-frame telemetry
    POST /api/video                upload an .mp4 for Benchmark 2; returns its probed facts
    GET  /runs/{run_id}/...        frames.csv, summary.json, report.pdf, scenario.yaml
One run at a time per server; a second request while one is live gets 409.
"""
from __future__ import annotations

import asyncio
import base64
import json
import math
import queue
import shutil
import threading
import time
import uuid
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from fsoc_tracker import __version__
from fsoc_tracker.engine.config import ATMOSPHERE_PRESETS, RunConfig, TargetConfig
from fsoc_tracker.engine.report import write_report
from fsoc_tracker.engine.simulation import Simulation
from fsoc_tracker.engine.sources import probe_video

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"
SCENARIOS = ROOT / "configs" / "scenarios"
RUNS = ROOT / "results" / "web"
UPLOADS = ROOT / "results" / "uploads"
RUNS.mkdir(parents=True, exist_ok=True); UPLOADS.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="FSOC Tracker web", version=__version__)
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


class Run:
    """One simulation running on a worker thread, publishing to a bounded queue."""

    def __init__(self, cfg: RunConfig, run_id: str, speed: float = 1.0):
        self.id = run_id
        self.cfg = cfg
        self.speed = speed            # 1 = real time, 0 = as fast as the server can
        self.out = RUNS / run_id
        self.subs: list[queue.Queue] = []      # one queue per connected viewer
        self.subs_lock = threading.Lock()
        self.last: dict | None = None            # latest message, sent first to a late viewer
        self.stop = threading.Event()
        self.done = threading.Event()
        self.summary = None
        self.error = None
        self.thread = threading.Thread(target=self._work, daemon=True)
        self.thread.start()

    def _work(self):
        try:
            sim = Simulation(self.cfg, self.out)
            self.sim = sim
            last_frame = 0.0
            next_t = time.perf_counter()
            for res in sim.steps():
                if self.stop.is_set():
                    break
                if self.speed > 0:            # pace to real time so the browser sees a video, not a blur
                    next_t += sim.dt / self.speed
                    lag = next_t - time.perf_counter()
                    if lag > 0:
                        time.sleep(lag)
                    else:
                        next_t = time.perf_counter()
                r = res.record
                msg = {"t": r.t_sim, "frame": r.frame, "mode": r.mode, "locked": r.locked, "tier": r.tier, "conf": r.confidence,
                       "n_cand": r.n_candidates, "pan": r.cam_pan_deg, "tilt": r.cam_tilt_deg, "cmd_pan": r.cmd_pan_rate, "cmd_tilt": r.cmd_tilt_rate,
                       "sat": int(r.sat_pan or r.sat_tilt), "det": [r.det_x, r.det_y], "est": [r.est_x, r.est_y], "vel": [r.vel_x, r.vel_y],
                       "true": [r.true_x, r.true_y], "terr": r.tracking_err_px, "cerr": r.centroid_err_px, "proc_ms": r.proc_ms,
                       "win": list(res.window), "probs": [r.p_cv, r.p_ca, r.p_ct], "unc": r.uncertainty_px,
                       "screen_w": self.cfg.screen.width, "screen_h": self.cfg.screen.height}
                now = time.perf_counter()
                if now - last_frame >= 1 / 12:          # picture at ~12 fps, telemetry every frame
                    last_frame = now
                    msg["scene"], msg["cam"] = self._pictures(res)
                for k, v in list(msg.items()):
                    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                        msg[k] = None
                    elif isinstance(v, list):
                        msg[k] = [None if (isinstance(x, float) and (math.isnan(x) or math.isinf(x))) else x for x in v]
                self._publish(msg)
            if self.stop.is_set():
                sim.finish()
            self.summary = sim.summary
            write_report(self.cfg, sim.telemetry.records, sim.summary, self.out / "report.pdf")
        except Exception as e:  # surface to the client
            import traceback
            self.error = traceback.format_exc()
        finally:
            self.done.set()
            self._publish({"end": True})

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=16)
        with self.subs_lock:
            self.subs.append(q)
            if self.last is not None:
                q.put(self.last)
            if self.done.is_set():
                q.put({"end": True})
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self.subs_lock:
            if q in self.subs:
                self.subs.remove(q)

    def _publish(self, msg: dict) -> None:
        """Fan out to every viewer; a slow viewer loses old messages, the engine never waits."""
        if not msg.get("end"):
            self.last = msg
        with self.subs_lock:
            for q in self.subs:
                if q.full():
                    try:
                        q.get_nowait()
                    except queue.Empty:
                        pass
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    pass

    def _pictures(self, res):
        img = res.observed
        gray = img if img.ndim == 2 else img
        H, W = gray.shape[:2]
        s = 640 / max(H, W)
        small = cv2.resize(gray, (int(W * s), int(H * s)), interpolation=cv2.INTER_AREA)
        x0, y0, w, h = res.window
        xa, ya = max(x0, 0), max(y0, 0); xb, yb = min(x0 + w, W), min(y0 + h, H)
        crop = np.zeros((h, w) if gray.ndim == 2 else (h, w, 3), np.uint8)
        if xb > xa and yb > ya:
            crop[ya - y0:yb - y0, xa - x0:xb - x0] = gray[ya:yb, xa:xb]
        lo, hi = np.percentile(crop[::4, ::4], (1, 99.8))
        if hi - lo > 8:
            crop = np.clip((crop.astype(np.float32) - lo) * (255.0 / (hi - lo)), 0, 255).astype(np.uint8)
        ok1, j1 = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 70])
        ok2, j2 = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return base64.b64encode(j1.tobytes()).decode(), base64.b64encode(j2.tobytes()).decode()


RUN: dict[str, Run] = {}
LOCK = threading.Lock()


def _active() -> Run | None:
    for r in RUN.values():
        if not r.done.is_set():
            return r
    return None


@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC / "index.html").read_text(encoding="utf-8")


@app.get("/api/scenarios")
def scenarios():
    out = []
    for p in sorted(SCENARIOS.glob("*.yaml")):
        cfg = RunConfig.load(p)
        out.append({"name": p.stem, "label": p.stem.replace("_", " "), "config": cfg.to_dict()})
    return {"scenarios": out, "defaults": RunConfig().to_dict(), "atmospheres": list(ATMOSPHERE_PRESETS), "version": __version__}


def _apply_overrides(cfg: RunConfig, ov: dict) -> RunConfig:
    """Whitelisted, typed overrides from the browser form."""
    for sec in ("screen", "camera", "disturbance", "tracker"):
        for k, v in (ov.get(sec) or {}).items():
            obj = getattr(cfg, sec)
            if hasattr(obj, k):
                cur = getattr(obj, k)
                setattr(obj, k, type(cur)(v) if not isinstance(cur, bool) else bool(v))
    t = ov.get("target") or {}
    if t:
        t0 = cfg.targets[0]
        for k, v in t.items():
            if hasattr(t0, k):
                cur = getattr(t0, k)
                setattr(t0, k, type(cur)(v))
    extra = int(ov.get("extra_targets", len(cfg.targets) - 1))
    rng = np.random.default_rng(int(ov.get("seed", cfg.seed)) + 99)
    motions = ["circular", "line", "figure8", "random", "sinusoidal"]
    targets = [cfg.targets[0]]
    for i in range(extra):
        if i + 1 < len(cfg.targets):
            targets.append(cfg.targets[i + 1])
        else:
            targets.append(TargetConfig(shape=["circle", "square", "gaussian"][i % 3], size_px=int(rng.integers(6, 16)), intensity=int(rng.integers(150, 235)),
                                        motion=motions[i % len(motions)], speed_px_s=float(rng.uniform(60, 180)), radius_px=float(rng.uniform(200, 450)),
                                        period_s=float(rng.uniform(8, 20)), heading_deg=float(rng.uniform(0, 360)), start="centre"))
    cfg.targets = targets
    if "seed" in ov:
        cfg.seed = int(ov["seed"])
    if "duration_s" in ov:
        cfg.duration_s = float(ov["duration_s"])
    if "name" in ov and str(ov["name"]).strip():
        cfg.name = "".join(c for c in str(ov["name"]) if c.isalnum() or c in "-_ ")[:40] or "run"
    return cfg


@app.post("/api/run")
async def start_run(body: dict):
    with LOCK:
        if _active() is not None:
            raise HTTPException(409, "a run is already in progress on this server; stop it or wait for it to finish")
        name = body.get("scenario")
        cfg = RunConfig.load(SCENARIOS / f"{name}.yaml") if name and (SCENARIOS / f"{name}.yaml").exists() else RunConfig()
        cfg = _apply_overrides(cfg, body.get("overrides") or {})
        if body.get("random_seed", True):
            cfg.seed = int(np.random.default_rng().integers(0, 10 ** 6))
            if cfg.targets[0].motion in ("line", "sinusoidal"):
                cfg.targets[0].heading_deg = float(np.random.default_rng(cfg.seed).uniform(0, 360))
        vid = body.get("video")
        if vid:
            p = UPLOADS / Path(vid).name
            if not p.exists():
                raise HTTPException(404, "uploaded video not found; upload it again")
            cfg.video = str(p); cfg.duration_s = 0.0; cfg.name = p.stem[:40]
        cfg.duration_s = min(cfg.duration_s, 120.0) if not cfg.video else 0.0
        cfg.output_dir = str(RUNS)
        run_id = time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
        speed = float(body.get("speed", 1.0))
        RUN[run_id] = Run(cfg, run_id, speed if speed in (0.0, 0.5, 1.0, 2.0, 4.0) else 1.0)
        # keep only the last 30 runs and the last 10 uploaded videos on disk
        for old in sorted(RUNS.iterdir())[:-30]:
            shutil.rmtree(old, ignore_errors=True)
        ups = sorted((u for u in UPLOADS.iterdir() if u.is_file()), key=lambda u: u.stat().st_mtime)
        for old in ups[:-10]:
            if str(old) != cfg.video:
                old.unlink(missing_ok=True)
        return {"run_id": run_id, "seed": cfg.seed, "config": cfg.to_dict()}


@app.post("/api/stop/{run_id}")
def stop_run(run_id: str):
    r = RUN.get(run_id)
    if not r:
        raise HTTPException(404, "unknown run")
    r.stop.set()
    return {"ok": True}


@app.post("/api/video")
async def upload_video(file: UploadFile = File(...)):
    suffix = Path(file.filename or "video.mp4").suffix.lower()
    if suffix not in (".mp4", ".avi", ".mov", ".mkv"):
        raise HTTPException(400, "please upload an .mp4, .avi, .mov or .mkv file")
    name = uuid.uuid4().hex[:8] + suffix
    dest = UPLOADS / name
    size = 0
    with open(dest, "wb") as f:
        while True:
            chunk = await file.read(1 << 20)
            if not chunk:
                break
            size += len(chunk)
            if size > 300 << 20:
                f.close(); dest.unlink(missing_ok=True)
                raise HTTPException(413, "video larger than 300 MB")
            f.write(chunk)
    try:
        info = probe_video(dest)
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, f"could not read this video: {e}")
    cap = cv2.VideoCapture(str(dest)); ok, bgr = cap.read(); cap.release()
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) if ok and bgr.ndim == 3 else bgr
    H, W = gray.shape[:2]; s = 640 / max(H, W)
    ok2, j = cv2.imencode(".jpg", cv2.resize(gray, (int(W * s), int(H * s))), [cv2.IMWRITE_JPEG_QUALITY, 70])
    info["upload"] = name; info["first_frame"] = base64.b64encode(j.tobytes()).decode()
    info["original_name"] = file.filename
    return info


def _json_safe(v):
    """NaN and infinity are not JSON; a metric with no value becomes null."""
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if isinstance(v, dict):
        return {k: _json_safe(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_json_safe(x) for x in v]
    return v


@app.get("/api/run/{run_id}")
def run_status(run_id: str):
    r = RUN.get(run_id)
    if not r:
        raise HTTPException(404, "unknown run")
    out = {"run_id": run_id, "done": r.done.is_set(), "error": r.error}
    if r.summary is not None:
        out["summary"] = _json_safe(r.summary.to_dict())
        out["files"] = {k: f"/runs/{run_id}/{k}" for k in ("report.pdf", "frames.csv", "summary.json", "scenario.yaml") if (r.out / k).exists()}
    return out


@app.get("/runs/{run_id}/{name}")
def run_file(run_id: str, name: str):
    if name not in ("report.pdf", "frames.csv", "summary.json", "scenario.yaml"):
        raise HTTPException(404)
    p = RUNS / run_id / name
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(str(p), filename=f"{run_id}_{name}")


@app.websocket("/ws/{run_id}")
async def ws(websocket: WebSocket, run_id: str):
    await websocket.accept()
    r = RUN.get(run_id)
    if not r:
        await websocket.close(code=4004); return
    loop = asyncio.get_event_loop()
    q = r.subscribe()
    try:
        while True:
            msg = await loop.run_in_executor(None, q.get)
            await websocket.send_text(json.dumps(msg))
            if msg.get("end"):
                break
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        r.unsubscribe(q)


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Browsers ask for this path by default; hand them the PNG."""
    return FileResponse(str(STATIC / "favicon-32.png"), media_type="image/png")


@app.get("/api/health")
def health():
    a = _active()
    return {"ok": True, "version": __version__, "busy": a.id if a else None, "busy_name": a.cfg.name if a else None}
