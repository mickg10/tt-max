# TT Max

Time-bounded CPU, memory and Tenstorrent stress testing, with a live web dashboard and a scriptable CLI. Built for QuietBox hosts; CPU and memory workloads also run without TT hardware.

## Run

```bash
uv run tt-max                         # dashboard on http://127.0.0.1:8765
uv run tt-max run                     # all CPUs + 1 GiB streaming RAM + all TT chips, 60s
uv run tt-max run --mode power --duration 120 --output results/power.json
uv run tt-max run --no-tt --cpu-workers 4 --memory-gb 2 --duration 30
uv run tt-max run --tt-devices 0,1 --cpu-workers 0 --memory-gb 0 --duration 60
uv run tt-max --help
```

Opening the dashboard starts monitoring only. Click **Start benchmark** to apply load; **Stop** cancels it. Choose duration, CPU workers, memory allocation, TT devices, matrix dimension and thermal cutoff. The maximum-power preset selects every logical CPU, all TT chips and at least 4096×4096 matrix multiplication. It stresses compute within existing firmware limits; it does not change clocks, voltages, power limits or firmware. Actual saturation and power depend on the device and workload.

For a remote host, tunnel the default dashboard:

```bash
ssh -L 8765:127.0.0.1:8765 quietbox4
cd ~/src/tt-max
~/.local/bin/uv run tt-max
```

Open `http://localhost:8765` locally. For a trusted network listener, set `TT_MAX_TOKEN` to a random access token, then run `uv run tt-max web --host 0.0.0.0`. Enter the token in the dashboard. The built-in server is HTTP; use an SSH tunnel or TLS reverse proxy on untrusted networks. Cross-origin mutations are rejected. No external frontend scripts or services are used.

## TT environment

The controller installs just NumPy and psutil through `uv`. TT workers use the existing TT-NN Python environment, so installing this project does not upgrade a working driver/runtime stack.

Default TT interpreter: `/opt/tenstorrent/venv/bin/python`. Override with `TT_MAX_TT_PYTHON` or:

```bash
uv run tt-max --tt-python /path/to/tt-venv/bin/python run --duration 60
```

That interpreter needs compatible `torch` and `ttnn`; `tt-smi` must be on PATH and the user must be allowed to open `/dev/tenstorrent/*`. TT-NN compiles kernels on first use. TT tensors are prepared and verified before CPU/memory stress starts, keeping initialization from competing with full CPU load. The timeout includes initialization and compilation; use 120 seconds for a cold cache if workers cannot finish a verified iteration within 60 seconds. The app refuses TT runs if TT-SMI reports existing device users. This preflight is advisory: coordinate with other users, because unrelated software can open devices after the check.

## What runs and what is measured

- **CPU:** one process per selected logical CPU, repeated single-threaded float32 BLAS matrix multiplication. BLAS threads are constrained to avoid accidental multiplication of parallelism.
- **Memory:** a separate process repeatedly writes the requested resident float64 array. This is a streaming workload, not a memory-integrity certification.
- **TT:** one process owns all selected chips (avoiding cross-process runtime discovery locks), tiled bfloat16 matrices, repeated `ttnn.matmul` into reused outputs. Each batch submits eight multiplies per chip before synchronizing all devices. The initial result on every chip is checked against a Torch reference before the worker becomes ready. TFLOPS is aggregate mathematical operations divided by host wall time, including dispatch/synchronization; it is not a vendor peak rating.
- **Telemetry:** CPU utilization, available/used RAM, CPU temperature where supported, per-chip power, temperature and clock, and board input power from TT-SMI. A p300c reports board power on both chips; the total counts each board once. Firmware power values can contain transient spikes and are not calibrated wall-power measurements.
- **Utilization:** TT-SMI 6.5.0 on Blackhole does **not** expose a true compute-utilization percentage. Hardware utilization is shown as unavailable. The separate worker kernel-duty percentage measures host time spent issuing/waiting for operations and must not be interpreted as Tensix occupancy.

Runs default to 60 seconds, accept 1–3600 seconds, and allow up to 10 additional seconds for worker cleanup. Start, stop, failure and shutdown all clean up this app's worker process groups. Workers also carry their own monotonic deadline and receive a parent-death kill signal on Linux. Cooperating TT Max controllers share a host-wide file lock across Unix users. The app never resets devices automatically; a hardware/runtime hang may require administrator recovery after forced termination.

Memory validation reserves at least 10% of total RAM or 2 GiB, including estimated worker overhead. An emergency stop triggers below 2% or 512 MiB available. TT runs stop when a selected chip reaches the configured 85°C default (or its lower firmware threshold), or telemetry disappears/becomes stale. A reported CPU temperature of 95°C also stops the run. These are software safeguards, not hard real-time guarantees; vendor thermal protections remain in effect.

## Reports and development

`--output results/run.json` saves configuration, per-worker iterations/rates/exit status, logs and sampled telemetry. The dashboard exposes the most recent full report at authenticated `GET /api/report`; `GET /api/status` returns the compact live view. `POST /api/start` accepts the CLI-equivalent JSON config; `POST /api/stop` accepts `{}`. Both require `Content-Type: application/json`.

```bash
uv sync --frozen --group dev
uv run pytest -q
```

Tests exercise real CPU/memory timeout and cancellation, memory/config limits, board-power deduplication, HTTP token authentication and cross-origin protection. See [VALIDATION.md](VALIDATION.md) for hardware verification.

Runtime references: [TT-NN API](https://docs.tenstorrent.com/tt-metal/latest/ttnn/) and [official TT-SMI telemetry fields](https://github.com/tenstorrent/tt-smi/blob/main/README.md).
