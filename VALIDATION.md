# Validation

2026-09-10, Python 3.12.

- `uv run pytest -q`: 19 passed. Includes real CPU and memory work, automatic timeout, cancellation, preflight cancellation without spawning, overlapping-controller exclusion, a thermal trip that stops a real worker, input/memory bounds, board power deduplication/missing values, HTTP token and cross-origin checks.
- Chromium desktop browser: started a five-second CPU + 0.25 GiB memory run through the GUI; reached `completed`, reported iterations, no browser errors. Started another run and stopped it; reached `cancelled` with no error.
- Local CLI: three-second run, two CPU workers + 0.05 GiB memory; every worker performed iterations and exited zero.
- Quietbox4 initial hardware probe: real TT-NN 2048×2048 bfloat16 matmul passed a Torch-reference check and sustained approximately 86 aggregate host-timed TFLOPS on one chip. CPU and memory workers ran correctly. Concurrent individual device owners serialized initialization, so that attempted multi-chip run correctly reported failure rather than success.

The implementation now uses one native TT-NN mesh for all selected chips. Full four-chip verification is pending the coordinated Quietbox4 BIOS maintenance window; do not interpret the initial single-chip result as validation of the mesh implementation.

TT-SMI 6.5.0 on this p300c host exposes power, temperature and clocks but no real compute-utilization percentage. Missing utilization remains unavailable, and p300c board power is counted once per board.
