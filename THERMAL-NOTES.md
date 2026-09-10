# Quietbox4 thermal investigation — 2026-09-10

## Follow-up: guarded CPU pulse and validation

CPU-only pilot `f886d5c9d64d` started at Unix 1789053424.8322458,
two CPU workers, zero memory workers, TT disabled, planned timeout 60 seconds.
An external one-second watchdog stopped it at 1789053425.8507438 after
observing 91.25 C against its conservative 80 C threshold. The threshold is
a reactive stop, not a guaranteed temperature ceiling. No second pulse was
launched. The native 95 C guard was not raised.

SQLite snapshot retained on nas642 and q4 at
`/tmp/tt-thermal-model-20260910.sqlite3`, made with SQLite online backup.
The recorded CPU jumped from 54.125 to 91.25 C; package energy-derived power
was 49.12 W over that sample interval, not an instantaneous peak power.
It returned to approximately 19 W within several seconds. Fitting CPU data
between Unix 1789053428 and 1789053486 gives a local apparent decay constant
of 6.54 seconds, floor 54.04 C, RMSE 0.081 C. Sensor filtering may contribute;
this is not a calibrated block resistance or a coolant temperature.

TT temperature medians in the minute before / minute after the pulse:
`[39.4,40.4,39.1,40.5]` / `[39.4,40.4,39.1,40.4]` C.
No clear cross heating is resolved. A one-second pulse deposits too little
energy to rule out coupling through a minutes-scale loop. TT chip power had
brief telemetry excursions, so perfect constant receiver power is not assumed.

Held-out-tail check on the earlier 403-sample passive trace: ten-second
medians, train from 30 to 420 seconds, forecast the remaining 39 bins without
refitting. Common tau estimated from training alone: 190.92 seconds.
Held-out RMSE CPU/TT0/TT1/TT2/TT3:
`[0.525,0.359,0.295,0.278,0.313]` C. A constant forecast using the median of
the final six training bins yields `[0.452,0.242,0.250,0.412,0.332]` C.
Thus the decay forecast is not consistently better than simple persistence.
This is a same-cooldown holdout, NOT independent cross-heating validation.
The 151–191-second results demonstrate fitting sensitivity; none is a
confidence interval or a measured liquid residence time.

Current conclusion: evidence supports two apparent timescales (fast CPU-local,
slow common cooling after mixed load). It is consistent with loop heat soak,
but does not establish coolant temperature, adequate flow, or radiator fault.
Further active pulses are on hold after the fast CPU excursion. Needed next:
CPU block model and visible inlet/outlet/loop routing, plus radiator-intake
air temperature or a verified coolant/flow reading. No cooling-control writes
or physical plumbing changes have been made. Goal remains incomplete.

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
