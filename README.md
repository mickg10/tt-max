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

Open `http://localhost:8765` locally. For a network listener, run `uv run tt-max web --host 0.0.0.0`. When `TT_MAX_TOKEN` is unset or empty, no token is required: anyone who can reach the dashboard can start benchmarks. Set `TT_MAX_TOKEN` to a random access token to require authentication, then enter it in the dashboard. The built-in server is HTTP; use an SSH tunnel or TLS reverse proxy on untrusted networks. Cross-origin mutations are rejected. No external frontend scripts or services are used.

## Docker Compose (Linux QuietBox hosts)

The image contains the controller and its locked Python dependencies. Compose mounts the already-tested `/opt/tenstorrent` runtime **read-only**, including TT-NN, its Python interpreter and SFPI. KMD and firmware remain host-managed. This is not a portable, self-contained TT-NN image: use the verified QuietBox layout described below.

```bash
python3 docker-preflight.py
docker compose build
# Set the real host name; optional token and listener settings are in .env.example.
TT_MAX_HOSTNAME=tt-quietbox4 docker compose up -d
docker compose ps
docker compose logs --tail 100
```

The native service and container cannot both bind port 8765. For a deliberate cutover, stop any benchmark, run `sudo systemctl stop tt-max`, then `docker compose up -d`. Only after validation disable the native service with `sudo systemctl disable tt-max`. Roll back with `docker compose down` followed by `sudo systemctl enable --now tt-max`. These actions are manual; the Compose files never stop host services themselves.

For monitoring-only validation alongside the native service:

```bash
TT_MAX_PORT=18765 TT_MAX_BIND=127.0.0.1 docker compose -p tt-max-validation up -d
# No benchmark starts on launch. Query the test dashboard through localhost/SSH.
TT_MAX_PORT=18765 TT_MAX_BIND=127.0.0.1 docker compose -p tt-max-validation down
```

Requirements and isolation boundaries:

- Ubuntu 24.04 container userspace, Linux Docker Engine and Compose. The current q2/3 shared Python under `/opt/tenstorrent/python` and q4 `/usr/bin/python3.12` layouts are supported. A venv symlink into a private home is rejected by preflight.
- All TT devices are exposed, with host PID/IPC/network namespaces so TT-SMI sees other processes and host telemetry. This is a **trusted host-management workload**, not an isolation boundary for untrusted users. No `privileged` mode, Docker socket, IPMI device, or writable host sysfs is granted. Capabilities are limited to process inspection and memory locking.
- The read-only bind of `/tmp/tt-max.run.lock` shares the exact native-controller lock inode. Run preflight again after a host reboot if `/tmp` was cleared; recreate the container if the host lock inode changes. Never remove that lock while a controller is running.
- Compiled-kernel caches persist in a named volume; each n300 board has a separate cache directory. `/reports` is another volume for CLI `--output /reports/run.json`. Dashboard report state remains in memory and is lost on restart.
- Stop has a 30-second grace period for worker cleanup. Restart policy restarts the **idle dashboard**, never a benchmark. Health checks test HTTP availability, not accelerator computation.
- Defaults remain a 60-second workload, 48-hour maximum, optional token, and port 8765 on all host interfaces. Set `TT_MAX_TOKEN` for authentication. Do not run simultaneous high-power tests across boxes sharing a circuit.

To smoke-test the image on a machine without TT hardware, without starting load:

```bash
docker build -t tt-max:local .
docker run --rm -p 127.0.0.1:18765:8765 tt-max:local
```

## TT environment

The controller installs just NumPy and psutil through `uv`. TT workers use the existing TT-NN Python environment, so installing this project does not upgrade a working driver/runtime stack.

Default TT interpreter: `/opt/tenstorrent/venv/bin/python`. Override with `TT_MAX_TT_PYTHON` or:

```bash
uv run tt-max --tt-python /path/to/tt-venv/bin/python run --duration 60
```

That interpreter needs compatible `torch` and `ttnn`; `tt-smi` must be on PATH and the user must be allowed to open `/dev/tenstorrent/*`. TT-NN compiles kernels on first use. TT tensors are prepared and verified before CPU/memory stress starts, keeping initialization from competing with full CPU load. The timeout includes initialization and compilation; use 120 seconds for a cold cache if workers cannot finish a verified iteration within 60 seconds. The app refuses TT runs if TT-SMI reports existing device users. This preflight is advisory: coordinate with other users, because unrelated software can open devices after the check.

### Disconnected n300 boards (quietbox2/3)

Four disconnected n300 boards contain eight chips, but cannot form one eight-chip mesh. TT Max groups TT-SMI rows by their shared **board serial**, resolves the host chip's PCI address through `/sys/class/tenstorrent/tenstorrent!N/device`, and uses the corresponding `/dev/tenstorrent/N` ID. It launches one worker per selected board concurrently. Each gets `TT_VISIBLE_DEVICES=N`, a separate `TT_METAL_CACHE`, and a native two-chip mesh with runtime-local IDs `0,1`. Both device outputs must pass the initial Torch-reference check before that worker is ready; CPU/memory stress waits until every selected board is ready.

`--tt-devices` and the dashboard use **global TT-SMI chip IDs**, not PCIe node IDs. A subset must include both chips sharing a board serial. A partial pair is rejected with the required IDs; it never silently expands your selection. `all` and the maximum-power preset select all four boards/eight chips. Quietbox4's Blackhole behavior remains one native mesh across its four chips.

For example, this observed quietbox3 enumeration has shuffled remote-chip and driver-node ordering:

| TT-SMI chip pair | Host PCI address | Worker visibility | Worker-local chips |
| --- | --- | --- | --- |
| `0,5` | `0000:01:00.0` | `/dev/tenstorrent/1` | `0,1` |
| `1,6` | `0000:41:00.0` | `/dev/tenstorrent/2` | `0,1` |
| `2,4` | `0000:42:00.0` | `/dev/tenstorrent/3` | `0,1` |
| `3,7` | `0000:c1:00.0` | `/dev/tenstorrent/0` | `0,1` |

Thus `uv run tt-max run --tt-devices 0,5 --cpu-workers 0 --memory-gb 0` selects one board in that enumeration. IDs can change after a reboot; the app reads the current SMI/serial/sysfs mapping each run. Board serials appear in the device table; PCI addresses are available on hover. Missing or ambiguous mappings stop preflight before workers launch. Each report includes `tt_plan` and separate global `devices` / `runtime_devices` fields, so per-board progress cannot be mistaken for a different global chip.

See Tenstorrent's [device-visibility and concurrent-process guidance](https://github.com/tenstorrent/tt-metal/blob/main/tech_reports/Programming_Mesh_of_Devices/Programming_Mesh_of_Devices_with_TT-NN.md#23-controlling-device-visibility). Hardware acceptance of this n300 path is separate from the existing quietbox4 validation; see [VALIDATION.md](VALIDATION.md).

## What runs and what is measured

- **CPU:** one process per selected logical CPU, repeated single-threaded float32 BLAS matrix multiplication. BLAS threads are constrained to avoid accidental multiplication of parallelism.
- **Memory:** a separate process repeatedly writes the requested resident float64 array. This is a streaming workload, not a memory-integrity certification.
- **TT:** one native mesh on Blackhole, or one isolated two-chip mesh worker per n300 board. Each uses tiled bfloat16 matrices and repeated `ttnn.matmul` into reused outputs. Each batch submits eight multiplies per chip before synchronizing its mesh. The initial result on every chip is checked against a Torch reference before its worker becomes ready. TFLOPS is per-worker aggregate mathematical operations divided by host wall time, including dispatch/synchronization; it is not a vendor peak rating.
- **Telemetry:** CPU utilization, available/used RAM, CPU temperature where supported, per-chip power, temperature and clock, and board input power from TT-SMI. A p300c reports board power on both chips; the total counts each board once. Firmware power values can contain transient spikes and are not calibrated wall-power measurements.
- **Utilization:** TT-SMI 6.5.0 on Blackhole does **not** expose a true compute-utilization percentage. Hardware utilization is shown as unavailable. The separate worker kernel-duty percentage measures host time spent issuing/waiting for operations and must not be interpreted as Tensix occupancy.

Runs default to 60 seconds, accept 1–172800 seconds (48 hours), and allow up to 10 additional seconds for worker cleanup. Start, stop, failure and shutdown all clean up this app's worker process groups. Workers also carry their own monotonic deadline and receive a parent-death kill signal on Linux. Cooperating TT Max controllers share a host-wide file lock across Unix users. The app never resets devices automatically; a hardware/runtime hang may require administrator recovery after forced termination. Historical telemetry is sampled at up to 3600 points per run; live monitoring and thermal checks remain at their normal cadence.

Memory validation reserves at least 10% of total RAM or 2 GiB, including estimated worker overhead. An emergency stop triggers below 2% or 512 MiB available. TT runs stop when a selected chip reaches the configured 85°C default (or its lower firmware threshold), or telemetry disappears/becomes stale. A reported CPU temperature of 95°C also stops the run. These are software safeguards, not hard real-time guarantees; vendor thermal protections remain in effect.

## Reports and development

### Continuous thermal database

The dashboard records continuously at a target of one row per second, including idle/cooldown periods. SQLite uses WAL and persists across service restarts. Default: `~/.local/share/tt-max/telemetry.sqlite3`; override with `TT_MAX_DB`. Compose stores it in the `telemetry` volume. Run-report downsampling does not affect this database.

Rows contain UTC Unix timestamps, benchmark ID/state/config, CPU temperature/utilization, TT temperatures and chip/board power, CPU-minus-each-TT temperature deltas, raw motherboard fan RPM/PWM/temperature channels, and available RAPL energy/power domains. CPU package and its child core domain must not be summed. Unreadable counters remain null with an error; no watts are inferred from utilization. Sensor labels are preserved: motherboard temperatures are not labeled coolant or ambient without physical verification.

TT-SMI is polled independently at a one-second target; if a call is slower, records retain the last sample with its original `sampled_at` and `tt_age_seconds`. Thus one database row per second does not falsely imply every hardware sensor supplied a fresh reading. Recorder failures appear as `recording_error` in live telemetry. No automatic deletion/retention policy is applied; monitor disk space and archive as needed.

Scrape `GET /api/history?after=0&limit=1000`, using the returned `next_after` as the next cursor (limit 1–3600). Existing token/origin protections apply. Each row has a monotonic database `sample_id` independent of wall-clock adjustments. Direct SQL: `SELECT id,timestamp,run_id,payload FROM samples ORDER BY id;`. Use SQLite's online backup API or `.backup` while the service runs; copying only the main file can omit WAL data.

On native Linux services, root can install `power-counter-access.py` and run it before service start with the dedicated service group as its argument. This changes only group ownership/read permission of RAPL `energy_uj` files, not power limits. Sysfs permissions may reset at reboot/device re-creation. Do not make counters world-readable or run the entire dashboard as root solely for this access.

`--output results/run.json` saves configuration, per-worker iterations/rates/exit status, logs and sampled telemetry. The dashboard exposes the most recent full report at authenticated `GET /api/report`; `GET /api/status` returns the compact live view. `POST /api/start` accepts the CLI-equivalent JSON config; `POST /api/stop` accepts `{}`. Both require `Content-Type: application/json`.

```bash
uv sync --frozen --group dev
uv run pytest -q
```

Tests exercise real CPU/memory timeout and cancellation, memory/config limits, board-power deduplication, HTTP token authentication and cross-origin protection. See [VALIDATION.md](VALIDATION.md) for hardware verification.

Runtime references: [TT-NN API](https://docs.tenstorrent.com/tt-metal/latest/ttnn/) and [official TT-SMI telemetry fields](https://github.com/tenstorrent/tt-smi/blob/main/README.md).
# Low-host-overhead TT thermal tests

The start API accepts `"tt_trace": true` (opt-in; default false). Use it with
`"mode":"balanced", "cpu_workers":0, "memory_gb":0, "tt":true`.
Power mode enables CPU workers and is **not** a TT-only thermal test.
Trace mode warms the reusable-output program, captures 256 matmuls, verifies
replay numerically, waits 20 seconds for host setup cooldown, and replays with
host sleeps before synchronization. The total timeout includes all setup.
Reported TFLOP/s counts completed replay work; trace-mode hardware utilization
is not inferred from wall time. Measure actual CPU package power throughout.

On quietbox4 a temporary 1.5 GHz CPU frequency cap was additionally needed
to prevent startup boost spikes. This cap is **not automatically applied**
by the app. Pilot orchestration restored all original CPU limits on exit.
Trace mode is hardware-tested on quietbox4 only; q2/3 are not yet validated.
