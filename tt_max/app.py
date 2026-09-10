from __future__ import annotations

import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import sys
import time
from urllib.parse import urlparse

from .engine import Engine


def handler(engine, token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, status, body, content_type="application/json"):
            data = json.dumps(body, allow_nan=False).encode() if content_type == "application/json" else body
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def authorized(self):
            if token and not hmac.compare_digest(self.headers.get("Authorization", ""), f"Bearer {token}"):
                self.send(401, {"error": "Enter the dashboard access token"})
                return False
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).netloc != self.headers.get("Host"):
                self.send(403, {"error": "Cross-origin requests are not allowed"})
                return False
            # Protect localhost mode against hostile DNS rebinding.
            if not token and self.server.server_address[0] in ("localhost", "127.0.0.1") and self.headers.get("Host", "").split(":")[0] not in ("localhost", "127.0.0.1"):
                self.send(403, {"error": "Use localhost, or configure an access token"})
                return False
            return True

        def do_GET(self):
            if self.path == "/":
                self.send(200, Path(__file__).with_name("static").joinpath("index.html").read_bytes(), "text/html; charset=utf-8")
                return
            if not self.authorized():
                return
            if self.path == "/api/status":
                self.send(200, engine.snapshot())
            elif self.path == "/api/info":
                self.send(200, engine.info())
            elif self.path == "/api/report":
                self.send(200, engine.report())
            else:
                self.send(404, {"error": "Not found"})

        def do_POST(self):
            if not self.authorized():
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 <= length <= 16384:
                    raise ValueError("Request too large")
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ValueError("Expected application/json")
                raw = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(raw, dict):
                    raise ValueError("Expected an object")
                if self.path == "/api/start":
                    self.send(200, engine.start(raw))
                elif self.path == "/api/stop":
                    self.send(200, engine.stop())
                else:
                    self.send(404, {"error": "Not found"})
            except (ValueError, TypeError) as exc:
                self.send(400, {"error": str(exc)})
    return Handler


def main():
    parser = argparse.ArgumentParser(description="TT Max — bounded CPU, memory and Tenstorrent stress testing")
    parser.add_argument("--tt-python", default=os.environ.get("TT_MAX_TT_PYTHON"), help="Python interpreter with torch and ttnn installed")
    subs = parser.add_subparsers(dest="command")
    web = subs.add_parser("web", help="Launch live dashboard (default)")
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int, default=8765)
    web.add_argument("--token", default=os.environ.get("TT_MAX_TOKEN"), help="Optional access token (prefer TT_MAX_TOKEN env); unset allows unauthenticated access")
    run = subs.add_parser("run", help="Run a benchmark in the terminal")
    run.add_argument("--duration", type=int, default=60, help="Total time budget, 1–172800 seconds (48 hours); default 60")
    run.add_argument("--cpu-workers", type=int, default=os.cpu_count() or 1)
    run.add_argument("--memory-gb", type=float, default=1)
    run.add_argument("--no-tt", action="store_true")
    run.add_argument("--tt-devices", default="all", help="Global TT-SMI chip IDs; n300 subsets must include both chips of each selected board")
    run.add_argument("--matrix-size", type=int, default=2048)
    run.add_argument("--mode", choices=["balanced", "power"], default="balanced")
    run.add_argument("--temperature-limit", type=int, default=85)
    run.add_argument("--output", type=Path, help="Write full JSON report including telemetry samples")
    args = parser.parse_args()
    if not args.command:
        args.command, args.host, args.port, args.token = "web", "127.0.0.1", 8765, os.environ.get("TT_MAX_TOKEN")
    if args.command == "web" and args.host not in ("127.0.0.1", "localhost") and not args.token:
        print("Warning: no access token; anyone who can reach this dashboard can start benchmarks.", flush=True)
    engine = Engine(args.tt_python)
    def interrupted(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    try:
        if args.command == "web":
            server = ThreadingHTTPServer((args.host, args.port), handler(engine, args.token))
            print(f"TT Max dashboard: http://{args.host}:{args.port} (no load until Start)", flush=True)
            try:
                server.serve_forever()
            finally:
                server.server_close()
        else:
            cfg = {key: getattr(args, key) for key in ("duration", "cpu_workers", "memory_gb", "tt_devices", "matrix_size", "mode", "temperature_limit")}
            cfg["tt"] = not args.no_tt
            engine.start(cfg)
            while engine.snapshot()["running"]:
                status = engine.snapshot()
                print(f"{status['run']['state']:>9} {status['run']['elapsed']:5.1f}/{args.duration}s | CPU {status['telemetry']['cpu_percent']:5.1f}%", flush=True)
                time.sleep(1)
            report = engine.report()
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps({k: v for k, v in report.items() if k not in ("samples", "logs")}, indent=2))
            if report["state"] == "failed":
                for line in report["logs"][-12:]:
                    print(line, file=sys.stderr)
                return 1
    except KeyboardInterrupt:
        print("Stopping workers…", flush=True)
        return 130
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        engine.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
