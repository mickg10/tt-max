# Quietbox4 thermal investigation — 2026-09-10

## First provisional plateau window

Supervisor journal at 2026-09-10 16:44:53 host time logged the first observed
qualifying five-minute window for run2ba8b0226ea4, about31.5min into the run:
CPU/TT slopes .0902/.0992/.0145/.0719/.0845 C/min. Supervisor also required
CPU and TT power stability between window halves (within max2W or5%).
Current sensor values near80C CPU and80–83C TT. This is a rolling-window
threshold crossing, not yet eight-hour stability. Throughput near304TFLOP/s
at this point versus~396 early, so do not describe it as equilibrium at the
initial cold-device power or throughput. Run continues; no settings changed.

## 25-minute checkpoint: strong cross-heating, not absolute coolant thermometry

Run2ba8b0226ea4 remains live under the original supervisor (observed1541s).
SQLite online-backup artifact `/tmp/tt-soak-25min.sqlite3` on nas642 and q4.
Compare seconds20–30 (host-cooldown before sustained replay, 10 samples)
with seconds1200–1500 (300 samples): CPU median57.375→78.875 C, package
power19.56→20.77 W. TT chip medians46.8/49.4/46.7/49.7→
79.15/82.4/79.6/81.8 C. TT summed-rail power155→439 W; early active
seconds60–180 median487.5 W. Initial stored heat from preceding tests remains
present, and the short pre-replay interval is not an equilibrium reference.
The21.5 C CPU rise at only1.2 W higher package power supports a substantial
shared thermal contribution, not an exclusively CPU-workload explanation.
Different hotspot placement and unmeasured air drift still limit attribution.

SYSTIN34→39 C; CPUTIN42→59 C (neither verified as air/coolant). Fan4/5
median1148/1145→1158/1156 RPM; inferred pump fan6 4804→4770 RPM.
PWM4/5/6 stayed255. No cooling-setting intervention occurred. Do not call
the5 C SYSTIN change a measured room-temperature change.

At25min recent5min slopes were CPU .117 and TT .175/.041/.129/.120 C/min.
Full plateau criterion not met. The original eight-hour run remains required;
do not mark complete from this checkpoint or restart it.

## Live measured-power fit, run 2ba8b0226ea4

Read-only snapshot `/tmp/tt-soak-live.sqlite3` on nas642/q4 captures the
first ~462 seconds. `uv run python -m tt_max.thermal_fit
/tmp/tt-soak-live.sqlite3 2ba8b0226ea4` fits CPU response to mean TT chip-rail
power, with free initial state and offset, ten-second bins, excluding first
60 seconds of setup. CPU package power bin means span 19.75–20.61 W.
Training through300s gives effective tau192s, held-out RMSE0.473 C over the
remaining ~155s. Fitting all available data gives tau222s. However, apparent
gain changes from .0362 to .00124 C per TT chip-rail watt and extrapolated
zero-TT-power CPU floor from58 to76 C. This is poor parameter identification,
not a physical gain/floor result. Nearly constant input makes free floor and
power gain confounded. Do not claim absolute water temperature or radiator
resistance from this fit. Need distinct power levels/cooldown and ambient.

Run remains under original eight-hour supervisor; latest live state must be
queried before acting. Initial minute-to-minute CPU slopes slowed from4.49
to3.11 C/min; TT summed rail power medians declined495→478W and chip clocks
also fell, so slowdown is not solely attributable to thermal equilibration.

## Eight-hour follow-up (user authorized 90 C cutoffs)

User requested 8 hours, terminating on CPU or any TT at 90 C. Added native
`cpu_temperature_limit` API field (default remains 95, this run uses 90),
TT limit90 and existing lower per-device firmware limits still apply.
CPU and memory workers0, trace replay2048, CPU temporary max1.5GHz.
Supervisor: transient root systemd unit `tt-thermal-soak-8h`, bounded28900s,
launches `/tmp/tt-capped-trace-pilot.py` and `/tmp/tt-trace-pilot.py`.
The first launch cancelled before workers because telemetry was not yet fresh
after app restart; no heat test occurred. Added baseline freshness wait before
starting and relaunched after confirming the original unit terminated.
Check live systemd/API state for current run identity and outcome; do not
restart a live run. Journal holds supervisor samples and plateau notices;
SQLite holds continuous one-second raw data. CPU limit restoration is in the
supervisor finally block. Plateau detection logs but does not stop the 8h run.
Native and external temperature cutoffs are reactive, not guaranteed peak
temperature ceilings. Remote dashboard access remains intentionally open.

## TT trace replay and shared heat experiment

Opt-in API `tt_trace: true` now captures 256 reusable-output matmuls and
replays with the CPU sleeping before synchronization. Setup requires warm-up
with the same output-buffer signature; initial failed capture was stopped,
not counted as valid compute. Numerical output checks cover all four chips.
Two CPU-limit pilot scripts live at `/tmp/tt-trace-pilot.py` and
`/tmp/tt-capped-trace-pilot.py` on nas642/q4. They temporarily set all q4 CPU
maximum frequencies to 1.5 GHz, run with CPU/memory workers off, and restore
the original 5582301 kHz maximums in a finally block. No permanent CPU cap.
No q2/3 restart or trace-mode hardware test was done.

Successful pilot `f3caec01f978`: 120 seconds including setup and 20-second
host cooldown; 87.25 seconds verified replay, 1955 iterations, about 380–400
aggregate effective TFLOP/s. CPU package power remained ~20 W while CPU
temperature rose from ~57.4 C before replay to 63.1 C at finish. Snapshot
and report: `/tmp/tt-trace-success.sqlite3` and
`/tmp/tt-trace-success-f3caec01f978.json` on nas642 and q4.

Extended experiment `9560d60ec324` started Unix 1789056195.153, requested
1200 seconds with the same conservative guards. It stopped after ~210
seconds, including 175 seconds replay, when TT3 reached 75.1 C (75 C guard).
CPU package power stayed about 20–21 W; CPU rose from ~60 C to 69.6 C.
3839 replay iterations completed. CPU limits restored and worker exited0.
No plateau was reached; do not report a measured equilibrium or claim the
requested run-to-stability task complete. The shared temperature rise at
near-constant CPU power is strong cross-heating evidence, consistent with
the liquid loop. It cannot distinguish loop heat from heated inlet air alone.
The model must retain the initially warm state from preceding tests.

`tt_max/thermal_rc.py` now implements the physical differential equations:

```
C_i dT_i/dt = Q_i - G_i (T_i - W)
C_w dW/dt = sum_i G_i (T_i - W) - H (W - A)
```

Optional room state:
`C_room dA/dt = H (W-A) - H_room (A-A_out)`.
This simplified room equation omits other room heat sources and direct
device-to-air losses; use measured inlet air when available instead of
fitting those missing effects arbitrarily. With constant heat and air,
equilibrium satisfies `W=A+sum(Q)/H` and `T_i=W+Q_i/G_i`.
The solver uses exact constant-input interval updates and explicit initial
states. Positive physical parameters still need calibration; absolute coolant
temperature, deposited-heat fractions and room parameters are not identified
from the present records. Tests check equilibrium, warming-room behavior and
input validation. A plateau check should require stable power and sustained
small slopes, not just a flattened trace caused by throttling or guard stop.

Recommended missing instrumentation: two Yocto-Meteo-V2-C units, one for
room air away from exhaust and one for air entering the radiator; actual
coolant temperature/flow is still preferable for isolating plumbing faults.

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
