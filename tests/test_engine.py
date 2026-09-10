import json
import threading
import time
import sys
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from tt_max.app import handler
from tt_max.engine import Engine, normalize_config, tt_snapshot


@pytest.mark.parametrize("cfg", [
    {"duration": 0}, {"duration": 3601}, {"duration": float("nan")},
    {"memory_gb": -1}, {"memory_gb": float("inf")}, {"memory_gb": 1e9},
    {"cpu_workers": -1}, {"tt": "true"}, {"matrix_size": 1025},
    {"tt_devices": "0,0"}, {"tt_devices": "-1"},
    {"tt": False, "cpu_workers": 0, "memory_gb": 0},
])
def test_invalid_limits(cfg):
    with pytest.raises(ValueError):
        normalize_config(cfg)


def test_board_power_deduplicated(monkeypatch):
    raw = {"device_info": [
        {"board_info": {"board_id": "card1"}, "telemetry": {"board_power": "114", "power": "15"}},
        {"board_info": {"board_id": "card1"}, "telemetry": {"board_power": "114", "power": "16"}},
        {"board_info": {"board_id": "card2"}, "telemetry": {"board_power": "111", "power": "15"}},
    ]}
    monkeypatch.setattr("tt_max.engine.shutil.which", lambda _: "/bin/tt-smi")
    monkeypatch.setattr("tt_max.engine.subprocess.run", lambda *a, **k: type("Result", (), {"stdout": json.dumps(raw)})())
    snapshot = tt_snapshot()
    assert snapshot["board_power_w"] == 225
    assert snapshot["devices"][0]["utilization_percent"] is None


def wait(engine):
    deadline = time.monotonic() + 15
    while engine.snapshot()["running"] and time.monotonic() < deadline:
        time.sleep(.1)
    assert not engine.snapshot()["running"]


def test_real_cpu_timeout_and_cancellation():
    engine = Engine()
    try:
        engine.start({"tt": False, "duration": 2, "cpu_workers": 1, "memory_gb": .01})
        wait(engine)
        assert engine.report()["state"] == "completed"
        assert all(w["iterations"] > 0 and w["exit_code"] == 0 for w in engine.report()["workers"])
        engine.start({"tt": False, "duration": 30, "cpu_workers": 1, "memory_gb": 0})
        time.sleep(.3)
        engine.stop()
        wait(engine)
        assert engine.report()["state"] == "cancelled"
        assert all(p.poll() is not None for p in engine.processes)
    finally:
        engine.close()


def test_http_token_and_origin():
    engine = Engine()
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler(engine, "test-token"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = f"http://127.0.0.1:{server.server_port}"
    try:
        assert urlopen(root).status == 200
        with pytest.raises(HTTPError) as exc:
            urlopen(root + "/api/status")
        assert exc.value.code == 401
        req = Request(root + "/api/status", headers={"Authorization": "Bearer test-token"})
        assert "telemetry" in json.load(urlopen(req))
        req = Request(root + "/api/start", data=b"{}", headers={"Authorization": "Bearer test-token", "Content-Type": "application/json", "Origin": "https://evil.example"})
        with pytest.raises(HTTPError) as exc:
            urlopen(req)
        assert exc.value.code == 403
    finally:
        server.shutdown()
        server.server_close()
        engine.close()


@pytest.mark.parametrize("token", [None, ""])
def test_network_listener_without_token(token):
    engine = Engine()
    server = ThreadingHTTPServer(("0.0.0.0", 0), handler(engine, token))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = f"http://127.0.0.1:{server.server_port}"
    try:
        headers = {"Host": "quietbox.example:8765"}
        assert "telemetry" in json.load(urlopen(Request(root + "/api/status", headers=headers)))
        headers.update({"Content-Type": "application/json", "Origin": "http://quietbox.example:8765"})
        assert urlopen(Request(root + "/api/stop", data=b"{}", headers=headers)).status == 200
        headers["Origin"] = "https://evil.example"
        with pytest.raises(HTTPError) as exc:
            urlopen(Request(root + "/api/stop", data=b"{}", headers=headers))
        assert exc.value.code == 403
    finally:
        server.shutdown()
        server.server_close()
        engine.close()


def test_cancel_during_preflight_starts_no_workers(monkeypatch):
    engine = Engine(tt_python=sys.executable)
    def preflight():
        if engine.run:
            engine.stop()
        return {"error": None, "processes": [], "devices": [{"id": 0}]}
    monkeypatch.setattr("tt_max.engine.tt_snapshot", preflight)
    try:
        engine.start({"tt": True, "duration": 20, "cpu_workers": 1, "memory_gb": 0})
        wait(engine)
        assert engine.report()["state"] == "cancelled"
        assert not engine.processes
    finally:
        engine.close()


def test_missing_board_power_is_unavailable(monkeypatch):
    monkeypatch.setattr("tt_max.engine.shutil.which", lambda _: "/bin/tt-smi")
    raw = {"device_info": [{"board_info": {"board_id": "x"}, "telemetry": {}}]}
    monkeypatch.setattr("tt_max.engine.subprocess.run", lambda *a, **k: type("Result", (), {"stdout": json.dumps(raw)})())
    assert tt_snapshot()["board_power_w"] is None


def test_overlapping_controllers_refused():
    first, second = Engine(), Engine()
    try:
        first.start({"tt": False, "duration": 30, "cpu_workers": 1, "memory_gb": 0})
        deadline = time.monotonic() + 5
        while not first.processes and time.monotonic() < deadline:
            time.sleep(.05)
        assert first.processes
        second.start({"tt": False, "duration": 5, "cpu_workers": 1, "memory_gb": 0})
        wait(second)
        assert second.report()["state"] == "failed"
        assert "Another TT Max controller" in second.report()["error"]
        assert not second.processes
    finally:
        first.close()
        second.close()


def test_thermal_trip_stops_real_worker(monkeypatch):
    engine = Engine()
    try:
        engine.start({"tt": False, "duration": 30, "cpu_workers": 1, "memory_gb": 0})
        deadline = time.monotonic() + 5
        while not engine.processes and time.monotonic() < deadline:
            time.sleep(.05)
        assert engine.processes
        with engine.lock:
            engine.telemetry["cpu_temperature_c"] = 100
        wait(engine)
        assert engine.report()["state"] == "failed"
        assert "CPU reached" in engine.report()["error"]
        assert all(proc.poll() is not None for proc in engine.processes)
    finally:
        engine.close()
