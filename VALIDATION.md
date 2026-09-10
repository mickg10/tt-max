# Validation

2026-09-10, Python 3.12. Verified on quietbox4 after BIOS 4.43 installation: Ryzen 7 9700X (16 logical CPUs), 249 GiB RAM, two p300c boards / four Blackhole chips, TT-NN 0.78.0, TT-SMI 6.5.0, KMD 2.11.0, firmware 19.15.0.

- `uv run pytest -q`: 19 passed. Includes real CPU and memory work, automatic timeout, cancellation, preflight cancellation without spawning, overlapping-controller exclusion, a thermal trip that stops a real worker, input/memory bounds, board power deduplication/missing values, HTTP token and cross-origin checks.
- Chromium desktop browser: started a five-second CPU + 0.25 GiB memory run through the GUI; reached `completed`, reported iterations, no browser errors. Started another run and stopped it; reached `cancelled` with no error. JSON report download verified.
- Local CLI: three-second run, two CPU workers + 0.05 GiB memory; every worker performed iterations and exited zero.
- Quietbox4 native mesh: all four chips passed initial Torch-reference output checks, then performed repeated matrix multiplication concurrently. A 45-second CLI run (2048 matrix, four CPU workers, 0.5 GiB streaming memory) completed with every worker exiting zero and 402.4 aggregate host-timed TT TFLOPS during the compute phase.
- Quietbox4 maximum-power CLI: 45 seconds, all 16 CPU workers, four TT chips, 4096 matrix, 1 GiB memory. Completed successfully; CPU reached 100%. Initial testing showed that starting CPU stress during TT preparation delayed initialization; the final implementation prepares TT first.
- Quietbox4 final GUI maximum-power run: 30-second total budget, all 16 CPU workers, four TT chips, 4096 matrix and 4 GiB memory. All 18 workers completed verified work and exited zero. TT preparation took approximately 5.6 seconds; TT compute ran for 24.4 seconds at **473.7 aggregate host-timed TFLOPS**. Peak sampled CPU utilization **100%**, CPU temperature **79.25°C**, TT temperature **59.0°C**. Started through the real web GUI, live telemetry rendered all four chips, no JavaScript errors, and downloaded the full JSON report.

All stress runs stopped at their configured deadlines. No TT Max workers or dashboard server were left running after verification. The app is deployed at `/home/mickg10/src/tt-max` and runs with `~/.local/bin/uv run tt-max`.

Reports are in `results/quietbox4-mesh.json`, `results/quietbox4-power.json` and `results/quietbox4-gui-power.json` in the deployed checkout and the local checkout. These generated files are intentionally ignored by Git.

TT-SMI 6.5.0 on this p300c host exposes power, temperature and clocks but no real compute-utilization percentage. Missing utilization remains unavailable, and p300c board power is counted once per board. Firmware power readings showed large transient spikes, including values above configured board limits; the UI exposes the reported data, but these measurements are **not calibrated wall-power readings**. Temperature and mathematical throughput figures above are separate measurements.

## n300 board isolation update

The n300 implementation was developed against the observed quietbox3 SMI board serials, non-adjacent chip pairs and sysfs PCI-to-device-node mapping supplied during host maintenance. No host was contacted, deployed to or stress-tested for this code-only update.

`uv run pytest -q`: **36 passed** locally. New checks cover all four board owners, complete-board subsets, shuffled global chip and PCI node numbering, missing/ambiguous serial/PCI mappings, overlapping nodes, and unchanged Blackhole mesh planning. A subprocess integration test launches four independent probe workers, verifies distinct visibility/cache environments and local `0,1` IDs, waits for all four before starting CPU load, and confirms cleanup if one board worker fails. These probes do not emulate TT compute or claim eight-chip hardware validation; that acceptance remains for the host-maintenance owner.
