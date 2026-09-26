"""Web application: the same Simulation as the desktop app, served to a browser.

    uvicorn webapp.server:app --host 127.0.0.1 --port 8095

Endpoints
    GET  /                         the app
    GET  /api/scenarios            names and contents of configs/scenarios/*.yaml
    POST /api/run                  start a run: {"scenario": name|null, "overrides": {...}, "video": upload id|null}
    POST /api/stop/{run_id}        stop early (the report is still written)
    POST /api/pause/{run_id}       pause or resume;  POST /api/step/{run_id}  one frame while paused
    POST /api/disturb/{run_id}     change the disturbances of the running simulation: {"disturbance": {...}}
    GET  /api/ui                   the shared interface definition (panel, tiles, texts), identical to the desktop app
    POST /api/scenario_yaml        the scenario file for the current panel (Save scenario)
    GET  /api/runs                 recent runs on this server with their files (Results)
    WS   /ws/{run_id}              live frames (scene, camera) and per-frame telemetry
    POST /api/check                scenario check and a named preview of the scene at t = 0
    POST /api/video                upload an .mp4 for Benchmark 2; returns its probed facts
    GET  /runs/{run_id}/{report|frames|summary|scenario}   the run's files, named FSOC_<kind>_<name>_seed<N>_<time>_<file>
One run at a time per server; a second request while one is live gets 409.
"""
from __future__ import annotations

import asyncio
import dataclasses
import base64
import copy
import json
import math
import queue
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from fsoc_tracker import __version__
from fsoc_tracker.engine.config import ATMOSPHERE_PRESETS, RunConfig, TargetConfig, clean_disturbance_changes
from fsoc_tracker.engine.report import write_report
from fsoc_tracker.engine.simulation import Simulation
from fsoc_tracker.engine.sources import probe_video
from fsoc_tracker.ui_shared import (DURATION_RANGE, SPEEDS, LiveTiles, camera_bottom, camera_crop, camera_top, extra_targets,
                                    final_tiles, front_end_bundle, new_random_seed, prepare_video_run, scene_header, status_text, summary_text,
                                    telemetry_lines, video_loaded_lines, video_preview_header, scenario_check, target_labels,
                                    video_beacons, video_targets, beacon_labels)
from fsoc_tracker.engine.checks import check_config

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"
SCENARIOS = ROOT / "configs" / "scenarios"
RUNS = ROOT / "results" / "web"
UPLOADS = ROOT / "results" / "uploads"
RUNS.mkdir(parents=True, exist_ok=True); UPLOADS.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="ARGUS web", version=__version__)
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
        self.pause = False
        self.step_once = False
        self.done = threading.Event()
        self.summary = None
        self.error = None
        # whoever starts the run gets this token; stop, pause, step and live changes need it, so a
        # visitor watching the run cannot control it
        self.token = uuid.uuid4().hex
        self.pending: list[dict] = []          # live changes asked for before the simulation exists
        self.pending_lock = threading.Lock()
        self.thread = threading.Thread(target=self._work, daemon=True)
        self.thread.start()

    def _work(self):
        try:
            sim = Simulation(self.cfg, self.out)
            with self.pending_lock:
                self.sim = sim
                for ch in self.pending:           # an edit made right after Start
                    sim.request_disturbance(ch)
                self.pending = []
            last_frame = 0.0
            next_t = time.perf_counter()
            live = LiveTiles()
            ifov = self.cfg.camera.ifov_deg
            names = self.cfg.target_names()
            following = names[sim.di] if names else ""
            total = getattr(sim.source, "n_frames", 0) or int(round(self.cfg.duration_s * self.cfg.camera.update_rate_hz))
            for res in sim.steps():
                while self.pause and not self.stop.is_set() and not self.step_once:
                    time.sleep(0.01)
                    next_t = time.perf_counter()
                self.step_once = False
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
                       "screen_w": self.cfg.screen.width, "screen_h": self.cfg.screen.height, "total": total, "ifov": ifov,
                       "capture": self.cfg.tracker.capture_radius_px, "lim": self.cfg.camera.max_pan_rate_deg_s,
                       "segment": r.segment, "live": sim.accepts_disturbance_changes}
                if r.segment:                 # the latest change, so any viewer's page can show it
                    ch = sim.changes[r.segment - 1]
                    msg["change"] = {"segment": ch["segment"], "t": ch["t_s"], "what": ch["what"],
                                     "status": status_text("changed", t=ch["t_s"], what=ch["what"])}
                live.push(r)
                now = time.perf_counter()
                if now - last_frame >= 1 / 15 or self.pause:     # picture and panel at ~15 fps, plot data every frame
                    last_frame = now
                    msg["scene"], msg["cam"] = self._pictures(res)
                    tr = res.track
                    msg["pred"] = list(tr.prediction) if tr.prediction is not None else [None, None]
                    msg["beacons"] = [list(b) for b in (res.frame.truth.beacons if (res.frame.truth and res.frame.truth.beacons) else [])]
                    msg["di"] = sim.di
                    msg["names"] = names
                    msg["tiles"] = live.tiles()
                    msg["tele"] = telemetry_lines(r, following)
                    top_state, top_detail = camera_top(r, ifov)
                    bottom, sat = camera_bottom(r)
                    msg["hud"] = {"scene": scene_header(res.observed.shape[1], res.observed.shape[0], ifov, r.t_sim),
                                  "top_state": top_state, "top_detail": top_detail, "bottom": bottom, "sat": sat}
                for k, v in list(msg.items()):
                    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                        msg[k] = None
                    elif isinstance(v, list):
                        msg[k] = [None if (isinstance(x, float) and (math.isnan(x) or math.isinf(x))) else x for x in v]
                self._publish(msg)
            if self.stop.is_set():
                sim.finish()
            self.summary = sim.summary
            write_report(self.cfg, sim.telemetry.records, sim.summary, sim.files["report"])
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
        crop = camera_crop(gray, res.window)          # the same display stretch as the desktop camera view
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


@app.get("/api/ui")
def ui():
    return front_end_bundle()


@app.get("/api/scenarios")
def scenarios():
    out = []
    for p in sorted(SCENARIOS.glob("*.yaml")):
        cfg = RunConfig.load(p)
        out.append({"name": p.stem, "label": p.stem.replace("_", " "), "config": cfg.to_dict()})
    return {"scenarios": out, "defaults": RunConfig().to_dict(), "atmospheres": list(ATMOSPHERE_PRESETS), "version": __version__}


def _typed(obj, k, v):
    """Set obj.k from browser input, keeping the field's type; unknown keys are ignored."""
    if not hasattr(obj, k):
        return
    cur = getattr(obj, k)
    try:
        if isinstance(cur, bool):
            setattr(obj, k, bool(v))
        elif isinstance(cur, (int, float)):
            setattr(obj, k, type(cur)(float(v)))
        elif isinstance(cur, str) or cur is None:
            setattr(obj, k, str(v))
    except (TypeError, ValueError):
        pass


def _number(ov: dict, key: str, cast, default, minimum=None):
    """A number from the browser form; a bad value is a 400 with the field named, not a 500."""
    if key not in ov:
        return default
    try:
        v = cast(ov[key])
    except (TypeError, ValueError):
        raise HTTPException(400, f"{key} must be a number, got {str(ov[key])[:20]!r}")
    if isinstance(v, float) and not math.isfinite(v):
        raise HTTPException(400, f"{key} must be a finite number")
    if minimum is not None and v < minimum:
        raise HTTPException(400, f"{key} must be at least {minimum}")
    return v


def _apply_overrides(cfg: RunConfig, ov: dict) -> RunConfig:
    """Whitelisted, typed overrides from the browser form. The page sends the full target list
    (it keeps one per 'Edit target'); older pages send one 'target' and a decoy count."""
    for sec in ("screen", "camera", "disturbance", "tracker"):
        for k, v in (ov.get(sec) or {}).items():
            _typed(getattr(cfg, sec), k, v)
    if isinstance(ov.get("targets"), list) and ov["targets"]:
        tl = []
        for d in ov["targets"][:1 + 8]:
            t = TargetConfig()
            for k, v in (d or {}).items():
                _typed(t, k, v)
            if not t.height_px:
                t.height_px = t.size_px
            tl.append(t)
        cfg.targets = tl
    else:
        t = ov.get("target") or {}
        for k, v in t.items():
            _typed(cfg.targets[0], k, v)
    extra = _number(ov, "extra_targets", int, len(cfg.targets) - 1)
    seed = _number(ov, "seed", int, cfg.seed, minimum=0)
    designated = _number(ov, "designated", int, cfg.designated)
    cfg.targets = extra_targets(cfg.targets[0], cfg.targets, max(0, min(extra, 8)), seed, bool(ov.get("identical", False)), designated)
    cfg.designated = designated
    if ov.get("designation") in ("auto", "appearance", "start", "cue"):
        cfg.designation = ov["designation"]
    if "designation_cue" in ov:
        cfg.designation_cue = str(ov["designation_cue"])[:40]
    cfg.seed = seed
    cfg.duration_s = _number(ov, "duration_s", float, cfg.duration_s)
    if "name" in ov and str(ov["name"]).strip():
        cfg.name = "".join(c for c in str(ov["name"]) if c.isalnum() or c in "-_ ")[:40] or "run"
    return cfg


@app.post("/api/check")
def check(body: dict):
    """Scenario check and a named preview of the scene at t = 0, as the desktop panel shows them."""
    cfg = _config_from(dict(body, random_seed=False))
    lines = scenario_check(cfg)
    out = {"lines": lines, "names": target_labels(cfg), "designated": cfg.designated_index(), "targets": cfg.to_dict()["targets"]}
    if not body.get("video"):
        from fsoc_tracker.world.renderer import World
        try:
            c2 = copy.deepcopy(cfg); check_config(c2)
            img, truth = World(c2).render()
            H, W = img.shape[:2]; sc = 640 / max(H, W)
            ok, j = cv2.imencode(".jpg", cv2.resize(img, (int(W * sc), int(H * sc)), interpolation=cv2.INTER_AREA), [cv2.IMWRITE_JPEG_QUALITY, 70])
            out.update(preview=base64.b64encode(j.tobytes()).decode(), positions=[list(b) for b in truth.beacons],
                       window=list(truth.window), screen_w=W, screen_h=H)
        except Exception:
            pass
    return out


@app.post("/api/run")
async def start_run(body: dict):
    with LOCK:
        if _active() is not None:
            raise HTTPException(409, "a run is already in progress on this server; stop it or wait for it to finish")
        name = body.get("scenario")
        cfg = RunConfig.load(SCENARIOS / f"{name}.yaml") if name and (SCENARIOS / f"{name}.yaml").exists() else RunConfig()
        cfg = _config_from(body)
        vid = body.get("video")
        if vid:
            p = UPLOADS / Path(vid).name
            if not p.exists():
                raise HTTPException(404, "uploaded video not found; upload it again")
            cfg.video = str(p); cfg.name = p.stem[:40]
            tr = body.get("truth")
            if tr:
                tp = UPLOADS / Path(tr).name
                if tp.exists():
                    cfg.video_truth = str(tp)
            prepare_video_run(cfg)
        cfg.duration_s = min(max(cfg.duration_s, DURATION_RANGE[0]), DURATION_RANGE[1]) if not cfg.video else 0.0
        cfg.output_dir = str(RUNS)
        run_id = time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
        speed = _number(body, "speed", float, 1.0)
        RUN[run_id] = Run(cfg, run_id, speed if speed in [v for _, v in SPEEDS] else 1.0)
        # keep only the last 30 runs and the last 10 uploaded videos on disk
        for old in sorted(RUNS.iterdir())[:-30]:
            shutil.rmtree(old, ignore_errors=True)
        ups = sorted((u for u in UPLOADS.iterdir() if u.is_file()), key=lambda u: u.stat().st_mtime)
        for old in ups[:-10]:
            if str(old) != cfg.video:
                old.unlink(missing_ok=True)
        chk = scenario_check(cfg)
        return {"run_id": run_id, "token": RUN[run_id].token, "seed": cfg.seed, "config": cfg.to_dict(), "label": run_label_of(cfg), "checks": chk,
                "status": status_text("running", name=cfg.name, seed=cfg.seed, out=f"results/{run_label_of(cfg)}")
                          + (f"   |   {chk[0]}" if chk else "")}


def _config_from(body: dict) -> RunConfig:
    """Scenario plus panel values, with the same seed and decoy rules as the desktop app."""
    name = body.get("scenario")
    if name and not (isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9_\-]{1,80}", name)):
        raise HTTPException(400, "scenario must be the plain name of a file in configs/scenarios")
    ov = body.get("overrides") or {}
    if not isinstance(ov, dict):
        raise HTTPException(400, "overrides must be an object of panel values")
    cfg = RunConfig.load(SCENARIOS / f"{name}.yaml") if name and (SCENARIOS / f"{name}.yaml").exists() else RunConfig()
    cfg = _apply_overrides(cfg, ov)
    if body.get("random_seed", True):
        new_random_seed(cfg)
    return cfg


def run_label_of(cfg: RunConfig) -> str:
    from fsoc_tracker.engine.naming import run_label
    return run_label(cfg)


def _controlled(run_id: str, token: str) -> "Run":
    """The run, if the caller started it (holds its token); a watcher gets 403."""
    r = RUN.get(run_id)
    if not r:
        raise HTTPException(404, "unknown run")
    if not token or token != r.token:
        raise HTTPException(403, "only the page that started this run can control it")
    return r


@app.post("/api/pause/{run_id}")
def pause_run(run_id: str, token: str = ""):
    r = _controlled(run_id, token)
    r.pause = not r.pause
    return {"paused": r.pause}


@app.post("/api/step/{run_id}")
def step_run(run_id: str, token: str = ""):
    r = _controlled(run_id, token)
    r.pause = True; r.step_once = True
    return {"paused": True}


@app.post("/api/disturb/{run_id}")
def disturb_run(run_id: str, body: dict, token: str = ""):
    """New disturbance settings for the running simulation; they take effect on its next frame."""
    r = _controlled(run_id, token or str(body.get("token", "")))
    if r.done.is_set():
        raise HTTPException(409, "the run is not in progress")
    if r.cfg.video:
        raise HTTPException(409, "a video run carries its own disturbances")
    d = body.get("disturbance")
    changes = clean_disturbance_changes(d) if isinstance(d, dict) else {}
    if not changes:
        raise HTTPException(400, "no usable disturbance settings given")
    with r.pending_lock:
        sim = getattr(r, "sim", None)
        if sim is None:
            r.pending.append(changes)             # the simulation is still being built
        else:
            sim.request_disturbance(changes)
    return {"queued": True, "status": status_text("changing")}


@app.post("/api/scenario_yaml")
def scenario_yaml(body: dict):
    import yaml
    cfg = _config_from(dict(body, random_seed=False))
    text = yaml.safe_dump(cfg.to_dict(), sort_keys=False)
    safe = "".join(c for c in cfg.name if c.isalnum() or c in "-_") or "custom"
    from fastapi.responses import Response
    return Response(text, media_type="application/x-yaml", headers={"Content-Disposition": f'attachment; filename="{safe}.yaml"'})


@app.get("/api/runs")
def runs():
    out = []
    for rid in sorted(RUN.keys(), reverse=True)[:20]:
        r = RUN[rid]
        files = getattr(r.sim, "files", {}) if hasattr(r, "sim") else {}
        out.append({"run_id": rid, "label": getattr(r.sim, "label", rid) if hasattr(r, "sim") else rid, "done": r.done.is_set(),
                    "files": {k: f"/runs/{rid}/{k}" for k in ("report", "frames", "summary", "scenario") if k in files and files[k].exists()}})
    return {"runs": out}


@app.post("/api/stop/{run_id}")
def stop_run(run_id: str, token: str = ""):
    r = _controlled(run_id, token)
    r.stop.set()
    return {"ok": True}


@app.post("/api/video")
async def upload_video(request: Request, file: UploadFile = File(...)):
    query = dict(request.query_params)
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
    cam = RunConfig().camera
    for k, cast in (("cam_w", int), ("cam_h", int), ("fov_w", float), ("fov_h", float)):
        v = query.get(k)
        if v not in (None, ""):
            try:                         # only shapes the description text; a bad value is left out
                setattr(cam, {"cam_w": "width", "cam_h": "height", "fov_w": "fov_w_deg", "fov_h": "fov_h_deg"}[k], cast(v))
            except ValueError:
                pass
    # the beacons the detector sees in the first frames: the page lists them as targets to designate
    beacons = video_beacons(dest, RunConfig().tracker)
    info["beacons"] = [{k: (round(v, 1) if isinstance(v, float) else v) for k, v in b.items()} for b in beacons]
    info["targets"] = [dataclasses.asdict(t) for t in video_targets(beacons)]
    info["beacon_labels"] = beacon_labels(beacons)
    info["loaded_text"] = video_loaded_lines(file.filename or name, info, cam)
    info["preview_header"] = video_preview_header(info)
    info["status"] = status_text("video", path=file.filename or name)
    return info


@app.post("/api/truth")
async def upload_truth(request: Request, file: UploadFile = File(...)):
    """Ground truth for the uploaded video: a CSV of frame (or t), x, y."""
    from fsoc_tracker.engine.sources import load_truth
    data = await file.read()
    if len(data) > 20 << 20:
        raise HTTPException(413, "truth file larger than 20 MB")
    name = uuid.uuid4().hex[:8] + ".csv"
    dest = UPLOADS / name
    dest.write_bytes(data)
    fps = float(request.query_params.get("fps") or 30.0)
    try:
        n = len(load_truth(dest, fps))
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, f"could not read this truth file: {e}")
    return {"truth": name, "frames": n, "original_name": file.filename,
            "status": f"Ground truth: {file.filename} ({n} frames). Errors and RMSE will be computed against it."}


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
        files = getattr(r.sim, "files", {}) if hasattr(r, "sim") else {}
        out["files"] = {k: f"/runs/{run_id}/{k}" for k in ("report", "frames", "summary", "scenario") if k in files and files[k].exists()}
        out["label"] = getattr(r.sim, "label", None) if hasattr(r, "sim") else None
        sv = out["summary"]
        vals, passed = sv.get("values", {}), sv.get("passed", {})
        lab = out["label"] or run_id
        out["tiles"] = final_tiles(vals, passed)
        out["summary_text"] = summary_text(vals, passed, f"results/{lab}/{lab}_frames.csv", f"results/{lab}/{lab}_report.pdf",
                                           sv.get("designation"), sv.get("checks"))
        out["status"] = status_text("finished", out=f"results/{lab}")
    return out


@app.get("/runs/{run_id}/{name}")
def run_file(run_id: str, name: str):
    r = RUN.get(run_id)
    files = getattr(r.sim, "files", {}) if (r is not None and hasattr(r, "sim")) else {}
    if name not in files or not files[name].exists():
        raise HTTPException(404)
    return FileResponse(str(files[name]), filename=files[name].name)


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
