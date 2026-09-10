# Quietbox4 thermal investigation — 2026-09-10

## Measured passive cooldown

Input artifact on nas642: `/tmp/tt-thermal-q4.jsonl`, 403 two-second
samples from the read-only collector beginning at Unix 1789052237.5769546.
This is older than the new one-second persistent recorder. No active dashboard
benchmark occurred in this selected trace. The preceding run had been mixed
CPU/TT load, so this is not a controlled cross-heating experiment.

Reproduce: `uv run python -m tt_max.thermal /tmp/tt-thermal-q4.jsonl`

Ten-second medians, excluding the first 30 seconds, fit
`T_i(t) = floor_i + amplitude_i * exp(-t/tau)` with free floors and
amplitudes and a common tau. The descriptive fit gives:

- tau: 160.7 seconds; changing the excluded interval to 60 or 120 seconds
  gives 160.0 or 151.5 seconds (sensitivity checks, not confidence bounds).
- Fitted initial remaining excess at the selected tail start: CPU 4.96 C;
  four TT chips 5.28, 5.47, 5.31, 5.43 C.
- RMSE on the fitted, binned data: CPU 0.36 C; TT 0.10–0.14 C.
- Fitted temperature floors: CPU 54.27 C; TT 39.55, 40.63, 39.38, 40.86 C.
  These are sensor floors under ongoing idle power, NOT water temperatures.
- Two-minute median CPU package power was approximately 17.6–18.9 W.

Interpretation: compatible with a shared slow thermal state and strengthens
the heat-soak hypothesis. Separate warm masses after mixed load can also
decay together. This fit has no held-out validation, does not account for all
power variation, and cannot identify radiator flow or absolute coolant
temperature. Motherboard SYSTIN is not a verified ambient thermometer.

## Next identification model

Use a shared state plus local device responses:

```
tau_w * dw/dt = -w + k_cpu * delta_Pcpu + k_tt * delta_Ptt + delta_Tair
tau_i * dy_i/dt = -y_i + w + r_i * delta_Pi
T_i = b_i + y_i
```

Fit positive gains and time constants, free floors and initial states. Keep
CPU package and core power separate; count each TT board input only once,
and analyze disagreeing board-input and chip-rail proxies separately.
Actual ambient remains missing. Detailed Astra theoretical report is at
`/tmp/tt-thermal-theory.md` on nas642.

Next experiment: bounded CPU-only pulse, cooldown, TT0/1 pulse, cooldown,
TT2/3 pulse, cooldown. Record actual receiver power and initialization work.
Use a conservative additional CPU stop threshold below the existing 95 C
guard; do not increase limits or change fan controls. Compare against an
independent two-timescale local model and validate on a whole repeat pulse.
No new identification load was launched during this fit.

## Recorder deployment / handoff

Continuous approximately 1 Hz SQLite recording is deployed on quietbox2/3/4.
History API: `/api/history?after=0&limit=1000`; page using `next_after`.
Native DB: `~/.local/share/tt-max/telemetry.sqlite3` under mickg10.
Includes raw available hwmon, RAPL, TT readings, freshness and run metadata.
No verified coolant/ambient sensor exists in these records.

Quietbox2 was briefly stopped with user approval, updated, and its previous
maximum-power settings restarted with the remaining original wall-time
budget (58150 seconds at restart). Quietbox3/4 remain available; check live
state before any experiment. Passive q4 collector was still running under
the original 1800-second timeout when last observed; do not duplicate it.
The new Docker telemetry volume is configured but images are not rebuilt.

43 tests passed. Thermal goal remains in progress: descriptive cooldown fit
complete; causal cross-heating identification and hardware diagnosis pending.
