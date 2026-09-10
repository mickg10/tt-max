from __future__ import annotations

import copy
import fcntl
import json
import math
import os
from pathlib import Path
import shutil
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
import uuid

import psutil

GIB = 1024 ** 3
WORKER = Path(__file__).with_name("worker.py")


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def tt_snapshot():
    command = shutil.which("tt-smi")
    if not command:
        return {"devices": [], "processes": [], "error": "tt-smi is not installed"}
    try:
        result = subprocess.run([command, "-s", "--snapshot_no_tty", "--offline"],
                                capture_output=True, text=True, timeout=8, check=True)
        raw = json.loads(result.stdout[result.stdout.index("{"):])
        devices = []
        for i, item in enumerate(raw.get("device_info", [])):
            telem = item.get("telemetry", {})
            board = item.get("board_info", {})
            limits = item.get("limits", {})
            devices.append({"id": i, "board_id": board.get("board_id"),
                            "bus_id": board.get("bus_id"), "type": board.get("board_type"),
                            "power_w": number(telem.get("power")),
                            "board_power_w": number(telem.get("board_power")),
                            "temperature_c": number(telem.get("asic_temperature")),
                            "clock_mhz": number(telem.get("aiclk")),
                            "power_limit_w": number(limits.get("tdp_limit")),
                            "thermal_limit_c": number(limits.get("therm_trip_l1_limit")),
                            "utilization_percent": number(telem.get("utilization"))})
        # Board input power is repeated for both chips on p300c; count each board once.
        boards = {d["board_id"] or d["bus_id"]: d["board_power_w"] for d in devices}
        return {"devices": devices, "processes": raw.get("processes", []), "error": None,
                "board_power_w": sum(v for v in boards.values() if v is not None) if any(v is not None for v in boards.values()) else None,
                "sampled_at": time.time()}
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        return {"devices": [], "processes": [], "error": str(exc)}


def normalize_config(raw):
    cfg = {"duration": 60, "cpu_workers": os.cpu_count() or 1, "memory_gb": 1,
           "tt": True, "tt_devices": "all", "matrix_size": 2048,
           "mode": "balanced", "temperature_limit": 85}
    unknown = set(raw) - set(cfg)
    if unknown:
        raise ValueError(f"Unknown options: {', '.join(sorted(unknown))}")
    cfg.update(raw)
    for key, low, high in (("duration", 1, 3600), ("cpu_workers", 0, os.cpu_count() or 1),
                           ("matrix_size", 256, 8192), ("temperature_limit", 40, 95)):
        value = cfg[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or int(value) != value or not low <= value <= high:
            raise ValueError(f"{key} must be an integer between {low} and {high}")
        cfg[key] = int(value)
    if cfg["matrix_size"] % 32:
        raise ValueError("matrix_size must be a multiple of 32")
    if not isinstance(cfg["tt"], bool):
        raise ValueError("tt must be true or false")
    if cfg["mode"] not in ("balanced", "power"):
        raise ValueError("mode must be balanced or power")
    memory = cfg["memory_gb"]
    if isinstance(memory, bool) or not isinstance(memory, (int, float)) or not math.isfinite(memory) or memory < 0:
        raise ValueError("memory_gb must be a finite nonnegative number")
    if not isinstance(cfg["tt_devices"], str):
        raise ValueError("tt_devices must be 'all' or comma-separated logical IDs")
    if cfg["tt_devices"] != "all":
        try:
            ids = [int(i) for i in cfg["tt_devices"].split(",")]
            if not ids or len(set(ids)) != len(ids) or min(ids) < 0:
                raise ValueError()
        except ValueError:
            raise ValueError("tt_devices must be 'all' or unique nonnegative IDs") from None
    if cfg["mode"] == "power":
        cfg["cpu_workers"] = os.cpu_count() or 1
        cfg["tt"] = True
        cfg["tt_devices"] = "all"
        cfg["matrix_size"] = max(cfg["matrix_size"], 4096)
        cfg["memory_gb"] = max(cfg["memory_gb"], 1)
    available = psutil.virtual_memory().available
    reserve = max(2 * GIB, psutil.virtual_memory().total * 0.1)
    # CPU matrices + interpreter overhead, and TT imports/host matrices, are separate from streaming RAM.
    device_count = max(1, len(list(Path("/dev/tenstorrent").glob("[0-9]*"))))
    overhead = cfg["cpu_workers"] * 96 * 1024 ** 2
    if cfg["tt"]:
        overhead += device_count * (512 * 1024 ** 2 + cfg["matrix_size"] ** 2 * 24)
    if cfg["memory_gb"] * GIB + overhead > max(0, available - reserve):
        raise ValueError("Requested load would breach the 10% / 2 GiB memory reserve")
    if not (cfg["cpu_workers"] or cfg["memory_gb"] or cfg["tt"]):
        raise ValueError("Select at least one workload")
    return cfg


class Engine:
    def __init__(self, tt_python=None):
        self.tt_python = tt_python or os.environ.get("TT_MAX_TT_PYTHON", "/opt/tenstorrent/venv/bin/python")
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.shutdown = threading.Event()
        self.run = None
        self.processes = []
        self.readers = []
        self.telemetry = {"cpu_percent": 0, "memory": {}, "tt": {"devices": [], "error": "Sampling…"}}
        self.thread = None
        self.monitor = threading.Thread(target=self._monitor, daemon=True)
        self.monitor.start()

    def info(self):
        return {"hostname": socket.gethostname(), "cpu_count": os.cpu_count() or 1,
                "memory_total_gb": round(psutil.virtual_memory().total / GIB, 1),
                "tt_available": bool(list(Path("/dev/tenstorrent").glob("[0-9]*"))),
                "tt_python": self.tt_python}

    def _monitor(self):
        psutil.cpu_percent()
        next_tt = 0
        while not self.shutdown.is_set():
            mem = psutil.virtual_memory()
            values = {"cpu_percent": psutil.cpu_percent(),
                      "memory": {"total": mem.total, "used": mem.used, "available": mem.available, "percent": mem.percent},
                      "timestamp": time.time()}
            try:
                sensors = psutil.sensors_temperatures()
                cpu_temps = [sensor.current for key, group in sensors.items()
                             if key in ("k10temp", "coretemp", "zenpower") for sensor in group]
                values["cpu_temperature_c"] = max(cpu_temps) if cpu_temps else None
            except (AttributeError, OSError):
                values["cpu_temperature_c"] = None
            if time.monotonic() >= next_tt:
                values["tt"] = tt_snapshot()
                next_tt = time.monotonic() + 2
            with self.lock:
                self.telemetry.update(values)
                if self.run and self.run["state"] == "running":
                    self.run["samples"].append(copy.deepcopy(self.telemetry))
            self.shutdown.wait(1)

    def snapshot(self):
        with self.lock:
            run = copy.deepcopy(self.run)
            if run:
                run["elapsed"] = min(run["duration"], (run.get("finished_at") or time.time()) - run["started_at"])
                run["progress"] = round(100 * run["elapsed"] / run["duration"], 1)
                run.pop("samples", None)
            return {"running": bool(run and run["state"] in ("starting", "running", "stopping")),
                    "run": run, "telemetry": copy.deepcopy(self.telemetry)}

    def start(self, raw):
        cfg = normalize_config(raw)
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise ValueError("A benchmark is already running")
            self.stop_event.clear()
            self.processes = []
            self.readers = []
            self.run = {"id": uuid.uuid4().hex[:12], "state": "starting", "config": cfg,
                        "duration": cfg["duration"], "started_at": time.time(),
                        "workers": [], "logs": [], "samples": [], "error": None}
            self.thread = threading.Thread(target=self._execute, args=(cfg,), daemon=True)
            self.thread.start()
        return self.snapshot()

    def _log(self, text):
        with self.lock:
            self.run["logs"].append(text[-2000:])
            self.run["logs"] = self.run["logs"][-100:]

    def _read(self, proc, worker):
        for line in proc.stdout:
            line = line.strip()
            try:
                values = json.loads(line)
                if isinstance(values, dict) and "event" in values:
                    with self.lock:
                        worker.update(values)
                    continue
            except ValueError:
                pass
            self._log(f"{worker['name']}: {line}")

    def _spawn(self, kind, deadline, **options):
        interpreter = self.tt_python if kind == "tt" else sys.executable
        cmd = [interpreter, "-u", str(WORKER), kind, "--deadline", str(deadline)]
        for key, value in options.items():
            cmd += [f"--{key}", str(value)]
        env = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
                   TT_METAL_LOGGER_LEVEL="ERROR")
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, start_new_session=True, env=env)
        worker = {"name": f"{kind}-{options.get('devices', len(self.processes))}", "kind": kind,
                  "pid": proc.pid, "event": "initializing", "devices": options.get("devices")}
        with self.lock:
            self.processes.append(proc)
            self.run["workers"].append(worker)
        reader = threading.Thread(target=self._read, args=(proc, worker), daemon=True)
        self.readers.append(reader)
        reader.start()

    def _execute(self, cfg):
        guard = None
        state = "completed"
        try:
            # Cooperating controllers share a host-wide lock across Unix users.
            # Linux permits flock(LOCK_EX) on a read-only descriptor. Reject symlinks.
            flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
            try:
                fd = os.open("/tmp/tt-max.run.lock", flags | os.O_CREAT | os.O_EXCL, 0o644)
                os.fchmod(fd, 0o644)
            except FileExistsError:
                fd = os.open("/tmp/tt-max.run.lock", flags)
            guard = os.fdopen(fd, "r")
            if not stat.S_ISREG(os.fstat(guard.fileno()).st_mode):
                raise RuntimeError("The TT Max lock path is not a regular file")
            try:
                fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("Another TT Max controller on this host is running a benchmark") from None
            ids = []
            if cfg["tt"]:
                if not Path(self.tt_python).is_file() and not shutil.which(self.tt_python):
                    raise RuntimeError(f"TT Python not found: {self.tt_python}; set --tt-python")
                preflight = tt_snapshot()
                if preflight["error"]:
                    raise RuntimeError(f"TT telemetry unavailable: {preflight['error']}")
                busy = [p for p in preflight["processes"] if "tt-smi" not in p.get("cmdline", "")]
                if busy:
                    raise RuntimeError(f"TT devices are already in use by PIDs: {[p['pid'] for p in busy]}")
                ids = [d["id"] for d in preflight["devices"]] if cfg["tt_devices"] == "all" else [int(i) for i in cfg["tt_devices"].split(",")]
                available_ids = {d["id"] for d in preflight["devices"]}
                if not ids or not set(ids) <= available_ids:
                    raise RuntimeError(f"Requested TT devices unavailable; found {sorted(available_ids)}")
                with self.lock:
                    self.telemetry["tt"] = preflight
            # Timeout covers worker startup/compilation, load, and normal run time.
            deadline = time.monotonic() + max(0, cfg["duration"] - (time.time() - self.run["started_at"]))
            if self.stop_event.is_set():
                state = "cancelled"
                return
            if time.monotonic() >= deadline:
                raise RuntimeError("Time budget expired during preflight; no workers started")
            with self.lock:
                self.run["state"] = "running"
            if ids:
                self._spawn("tt", deadline, devices=",".join(str(i) for i in ids), size=cfg["matrix_size"])
                self._log("Preparing and verifying TT tensors before starting CPU/memory load")
                while time.monotonic() < deadline and not self.stop_event.wait(.1):
                    self._check_health(cfg, ids)
                    with self.lock:
                        if self.run["workers"][0].get("verified"):
                            break
                if not self.stop_event.is_set() and time.monotonic() >= deadline:
                    raise RuntimeError("Time budget expired preparing TT; CPU/memory load was not started")
            for _ in range(cfg["cpu_workers"]):
                if self.stop_event.is_set() or time.monotonic() >= deadline:
                    break
                self._spawn("cpu", deadline)
            if cfg["memory_gb"] and not self.stop_event.is_set() and time.monotonic() < deadline:
                self._spawn("memory", deadline, bytes=int(cfg["memory_gb"] * GIB))
            while time.monotonic() < deadline and not self.stop_event.wait(0.2):
                self._check_health(cfg, ids)
            if self.stop_event.is_set():
                state = "cancelled"
        except Exception as exc:
            state = "failed"
            with self.lock:
                self.run["error"] = str(exc)
            self._log(str(exc))
        finally:
            with self.lock:
                self.run["state"] = "stopping"
            try:
                self._cleanup(graceful=state == "completed")
            except Exception as exc:
                state = "failed"
                self._log(f"Worker cleanup did not finish: {exc}")
                with self.lock:
                    self.run["error"] = f"Worker cleanup did not finish: {exc}"
            for reader in self.readers:
                reader.join(timeout=2)
            with self.lock:
                for p, worker in zip(self.processes, self.run["workers"]):
                    worker["exit_code"] = p.poll()
                if state == "completed" and any(w.get("iterations", 0) < 1 or w.get("exit_code") != 0 for w in self.run["workers"]):
                    state = "failed"
                    self.run["error"] = "Some workers did not finish valid work; increase duration for first-time TT compilation or inspect logs"
                self.run["state"] = state
                self.run["finished_at"] = time.time()
            if guard:
                guard.close()

    def _check_health(self, cfg, ids):
        failed = [p for p in self.processes if p.poll() not in (None, 0)]
        if failed:
            raise RuntimeError(f"Worker failed: PID {failed[0].pid}, exit {failed[0].returncode}; see log")
        if psutil.virtual_memory().available < max(512 * 1024 ** 2, psutil.virtual_memory().total * 0.02):
            raise RuntimeError("Stopped: available memory below emergency reserve")
        with self.lock:
            tt = copy.deepcopy(self.telemetry["tt"])
            cpu_temp = self.telemetry.get("cpu_temperature_c")
        if cpu_temp is not None and cpu_temp >= 95:
            raise RuntimeError(f"Stopped: CPU reached {cpu_temp} °C (95 °C cutoff)")
        if ids:
            if tt.get("error") or time.time() - tt.get("sampled_at", 0) > 12:
                raise RuntimeError("Stopped: TT telemetry unavailable or stale")
            if any(not any(d["id"] == i and d["temperature_c"] is not None for d in tt["devices"]) for i in ids):
                raise RuntimeError("Stopped: a selected TT device has no temperature reading")
            for d in tt["devices"]:
                if d["id"] in ids and d["temperature_c"] is not None:
                    limit = min(cfg["temperature_limit"], d.get("thermal_limit_c") or cfg["temperature_limit"])
                    if d["temperature_c"] >= limit:
                        raise RuntimeError(f"Stopped: TT {d['id']} reached {d['temperature_c']} °C (limit {limit})")

    def _cleanup(self, graceful=False):
        # Workers stop at their own deadline. Let interpreter/device teardown finish
        # before signaling; a signal during Python finalization can look like failure.
        if graceful:
            until = time.monotonic() + 2
            for proc in self.processes:
                try:
                    proc.wait(timeout=max(.01, until - time.monotonic()))
                except subprocess.TimeoutExpired:
                    pass
        for proc in self.processes:
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        until = time.monotonic() + 8
        for proc in self.processes:
            try:
                proc.wait(timeout=max(0.01, until - time.monotonic()))
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait(timeout=2)

    def stop(self):
        self.stop_event.set()
        return self.snapshot()

    def report(self):
        with self.lock:
            return copy.deepcopy(self.run)

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=20)
        self.shutdown.set()
