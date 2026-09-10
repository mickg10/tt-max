# Quietbox4 thermal investigation — 2026-09-10

## Passive cooldown assessment (18:36 UTC; no load restarted)

The user-ended run remains cancelled. The TT worker reported its final
`done` event and exit code 0; the soak supervisor is inactive. The recorder
continues at approximately 1 Hz with no recording error. At 18:34:32 UTC,
27.6 minutes after stopping, CPU Tctl was 55.875 C and TT temperatures were
41.0/42.3/40.8/42.8 C. CPU frequency maximums have already been restored;
no additional frequency changes, device resets or workloads were performed.

The first 25 minutes of cooldown and the original idle reference were
queried read-only from NAS ClickHouse, avoiding analysis work on q4. Frozen
aggregates, 210 ten-second bins, the exact query, fitting conventions and
results are in `thermal-analysis/20260910-q4-cooldown.json`. Temperatures
below are window medians; power is the arithmetic mean.

| Window | CPU C | TT0 / TT1 / TT2 / TT3 C | CPU package W | Summed TT rails W |
| --- | ---: | --- | ---: | ---: |
| Original 74-second idle reference | 54.25 | 39.4 / 40.4 / 39.1 / 40.5 | 18.83 | 60.77 |
| Last loaded minute, excluding final 5 s | 82.125 | 83.3 / 86.2 / 83.5 / 85.7 | 20.79 | 445.27 |
| 5–8 min after stop | 64.125 | 50.1 / 51.9 / 49.9 / 51.85 | 18.81 | 105.91 |
| 10–15 min after stop | 59.25 | 44.5 / 46.6 / 44.3 / 46.3 | 18.69 | 96.41 |
| 15–20 min after stop | 57.375 | 42.5 / 44.3 / 42.5 / 44.4 | 18.81 | 86.36 |
| 20–25 min after stop | 56.375 | 41.6 / 43.15 / 41.3 / 43.2 | 19.02 | 93.10 |

**The idle reference is not power-matched.** All four original idle clock
medians were 800 MHz. Following this run, TT1 and TT3 report 1350 MHz while
TT0 and TT2 report 800 MHz, despite the benchmark worker having exited.
The 20–25-minute mean TT powers are 21.99/27.01/14.10/30.00 W, versus
15.16/17.00/13.35/15.26 W originally. Clock telemetry alone does not prove
useful compute activity. These power and clock differences, residual
cooling, and unmeasured ambient prevent assigning the entire remaining
temperature excess to room heating. No clock reset was attempted.

The final loaded CPU was roughly 28 C above the original idle reference,
with package power differing by only about 2 W. By 20–25 minutes off, the
CPU excess was about 2.1 C. Together with the repeated local TT drop followed
by common cooling, this strongly supports a hot shared cooling environment
during the run. It does not establish an absolute coolant temperature or
partition the final heating tail into loop, room, or exhaust recirculation.

### One-pole cooldown fits fail the later cooling tail

A common exponential fitted to all five temperature channels during
30–300 s gives tau 222.94 s. Extending its frozen parameters over 300–1500 s
has per-channel RMSE 3.41/3.17/2.93/3.10/2.83 C. Its extrapolated CPU floor
61.04 C is plainly above the later observed CPU temperature. This is a
descriptive short-window decay, not a validated whole-loop time constant.
All these windows had already been observed; these are retrospective checks,
not prospective validation.

Power-aware one-pole CPU fits trained on the final 600 s loaded plus the
first 300 s off also fail the later 300–1500 s. Ten-second mean electrical
power and median temperature are used, excluding source samples with CPU
package power >=23 W or stale TT readings. Depending on whether the input
is summed chip rails or same-board min/max/mean INPUT_POWER, fitted taus
are 344–428 s; training RMSE is 0.41–0.42 C, later RMSE 2.05–4.79 C.
The ratio tau/gain spans 4.2–11.4 kJ/K and must NOT be called the physical
heat capacity: neither proxy is calibrated heat deposited into water, the
model fails its later interval, and inlet air is unmeasured.

For another consistency check, CPU cooling during 30–90 s is -5.071 C/min.
If every litre of the estimated 3–4 L followed that slope, water alone would
release 1.06–1.41 kW. The loaded-to-off chip-rail-plus-package power change
is about 309 W; the analogous mean-of-duplicate board proxy change is
about 699 W. Thus the joint assumptions of uniform water temperature,
calibrated heat input, unchanged inlet air and CPU exactly tracking water
are not established. The mismatch does not prove that the user's water
inventory is wrong. Local cooling paths and observation lag also matter.

### Relative thermal drops are better identified than absolute water

Near local equilibrium, `CPU - mean(TT)` approximately equals sensor-offset
difference plus `R_CPU*P_CPU - mean(R_TT*P_TT)`, with additional terms for
different local water temperatures. A uniform common water state cancels.
Repeated on/off changes give an apparent TT relative path around 0.18 K/W
under the common-water and constant-resistance assumptions. That is more
defensible than treating unloaded chips as exact water thermometers.

Illustratively, subtracting 0.15–0.20 K/W times approximately 111 W per chip
from roughly 84.7 C gives a loaded water estimate around 62–68 C. This is
an assumption-dependent sensitivity calculation, NOT a measured range or
confidence interval. Unknown sensor offsets and heat paths can shift it.
Consequently, the 90 C die guards must not be presented as protecting a
60 C coolant specification. A direct suitable coolant sensor and radiator
inlet-air measurement remain the discriminating measurements.

### Manufacturer specifications revise the mass sensitivity case

The canonical [TT-QuietBox 2 Blackhole specifications](https://docs.tenstorrent.com/systems/quietbox/quietbox-bh-2/specifications.html)
match q4's Ryzen 9700X, B850M-C and two p300c cards, and list **20 kg / 44 lb**
system weight, rather than the user's approximate 30 lb. Treat this as a
separate stock-system scenario, not a weighing of this individual machine.
With the user's 3–4 L water estimate and the same 0.4–0.9 kJ/(kg K) dry
material assumptions, the 20 kg case is approximately 19–31 kJ/K. At the
late 0.0278 C/min slope it stores roughly 9–14 W if all that mass follows
the common temperature. This does not reverse the near-heat-balance
conclusion and does not make all case mass part of the liquid loop.

The same canonical page lists up to 1100 W combined board power and 1300 W
system maximum. Those are product ratings, not measurements of this run;
do not replace the measured chip-rail domain with them. They also differ
from the newer illustrated guide's approximately 1500 W claim. Neither
document calibrates discrepant INPUT_POWER readings or the liquid/air split.
The [manufacturer FAQ](https://docs.tenstorrent.com/systems/quietbox/quietbox-bh-2/support-bh-2.html)
describes bottom/side intake, top exhaust and 25 cm clearance for airflow.
It does not specifically demand 25 cm under the factory feet. No physical
cooling or placement changes were made during this cooldown.

Current conclusion: substantial shared-sink heat soak is strongly supported;
exact coolant temperature and the room contribution are not identified.
The model goal remains in progress pending a measured boundary/coolant
reference; the experiment remains stopped and passive recording continues.

## User-ended soak and recorded shutdown transition (18:06:53 UTC)

User requested ending the soak. Stopped only q4 run `2ba8b0226ea4` through
`POST /api/stop` after revalidating its identity. Terminal state `cancelled`,
no error, finished Unix1789063613.4148362 after6807.21 s (113.45 min), not
the originally planned8 hours. TT worker39665 exited; supervisor
`tt-thermal-soak-8h.service` became inactive with Result=success, MainPID0.
All CPU scaling maximums were restored to5582301 kHz. The native recorder
and Grafana collection continue; no new load was launched and q2/3 were
not stopped. Recorded active/stopping maxima: CPU82.125 C and TT chips
84.2/86.6/84.5/86.2 C. No90 C cutoff was reached.

SQLite online backup: `/tmp/tt-soak-stop-2ba8b0226ea4.sqlite3` on q4, copied
to NAS `/tmp/tt-soak-stop-2ba8b0226ea4.utwMmP/telemetry.sqlite3` with an
`/api/report` export alongside as `report.json`. Snapshot size63,717,376
bytes; SQLite quick_check returnedok. Includes201.72 s after finish; the
live database continues recording subsequent cooldown. Maximum intersample
gap during this run plus captured cooldown was1.083 s.

The recorded transition (medians within each window) is:

| Time relative to finished_at | CPU C | Mean TT C | CPU minus mean TT C | CPU package W | Summed TT rail W |
| --- | ---: | ---: | ---: | ---: | ---: |
| -60 to-5 s | 82.125 | 84.550 | -2.450 | 20.811 | 430 |
| +5 to+15 s | 82.812 | 72.062 | 10.675 | 19.292 | 136 |
| +20 to+40 s | 81.375 | 70.138 | 11.200 | 19.274 | 137 |
| +55 to+75 s | 78.312 | 66.475 | 11.763 | 18.950 | 138 |
| +115 to+135 s | 74.125 | 61.812 | 12.200 | 19.081 | 127 |
| +175 to+195 s | 70.812 | 58.263 | 12.575 | 18.812 | 120 |

The rapid TT drop before CPU falls, followed by both cooling, supports
local TT self-heating superimposed on a shared cooling response. These
are not direct water-temperature readings. Idle TT power remains nonzero
and declines during cooldown; the restored CPU frequency limit and any
monitoring/analysis CPU work must be accounted for in subsequent fits.
At about5.7 min after stopping, API readings were CPU65.25 C and TT
51.2/53.1/51.0/53.2 C, with no recording error.

The user also supplied approximate room temperature20 C at the original
start, when TT temperature was roughly38 C. This is a useful user-reported
initial boundary anchor, not a time series or a timestamp-matched measurement
at the start of this already-warm113-minute run. Asked for another reading
at the same location. The18 C chip-to-room difference combines idle local
self-heating and the loop/inlet-to-room rise; it is not a measured radiator
delta-T or heat-transfer efficiency.

The120/180/240-minute heating forecasts below are invalidated by this
user-requested load change before the first forecast window. Preserve their
parameters, but do not score the cooler unloaded temperatures against them.
The thermal goal remains in progress through cooldown and model assessment.

## Revised mass constraint and late-tail forecasts (17:51 UTC)

User revised the estimate to **3–4 litres of water in a roughly 30 lb
(13.6 kg) complete computer**, with CPU and TT devices on the liquid loop,
motherboard RAM outside it, and few other heatsinks. This supersedes the
earlier under-3-litre estimate below. Water contributes roughly 12.5–16.7
kJ/K. Counting all remaining 9.6–10.6 kg with metal-like specific heats
0.4–0.9 kJ/(kg K) gives a whole-box scenario of about 17–26 kJ/K. Not all
that hardware follows coolant temperature; this is not a measured loop
capacity. A deliberately generous 36 kJ/K sensitivity case allows a much
higher average non-water specific heat. Neither range is a strict bound
without a material inventory and coupling information. Representative heat
capacities: [OpenStax reference table](https://openstax.org/books/physics/pages/a-reference-tables).

CPU package and TT chip telemetry do not contain motherboard DIMM power;
do not subtract a speculative RAM contribution from their sum. On q4,
tt-smi 6.5 reads chip power from the low 16 bits of firmware TDP, separately
from board INPUT_POWER; board readings remain discrepant across same-board
chips. Late TT chip-rail mean is approximately 450 W and CPU package about
21 W. Additional board memory, conversion losses, fans/pump and other
system heat are separate, incompletely measured quantities. This is not
a claim that exactly 471 W reaches the water or that a wall meter reads471 W.

CPU median rose80.25→81.5 C between window midpoints42.5→87.5 min, about
0.0278 C/min, at nearly constant measured power. At 0.02 C/min, the17–26
kJ/K scenario stores5.7–8.7 W; even36 kJ/K stores12 W. At0.05 C/min the
generous36 kJ/K case stores30 W. These estimates assume the represented
thermal mass shares the measured slope; CPU/TT sensors are not coolant
thermometers. If235–471 W is entering the loop, the late model is already
rejecting most of it. Hundreds of watts accumulating in a common-temperature
hidden computer mass is not a credible explanation of this slow drift.

This does NOT exclude a small, long internal tail. For a main lumped
radiator path, tau=C*delta_T_radiator/Q. Example C=20 kJ/K, Q=470 W and
water-to-inlet delta30 K gives tau21.3 min and about64 min to95% settling.
The same tau results from half the heat and half the delta. A small weakly
coupled mass can have another slow pole without storing much power.
Neither water-to-air delta nor captured heat has been measured.

The recorded CPU curve has an early fast rise and a slow tail. A retrospective
shape comparison trained on5-minute medians at7.5–62.5 min, then evaluated
at67.5–87.5 min, gives held-out RMSE0.684 C for one exponential,0.134 C
for two positive exponentials, and0.117 C for an exponential plus a ramp.
These data had already been inspected: this is NOT independent validation.
The latter two shapes fit similarly, and do not identify the slow state as
room air versus another internal mass. They omit actual power as an input.

Parameters and data are frozen in
`thermal-analysis/20260910-q4-cpu-tail.json`. Prospectively, at120 min the
two-exponential model predicts81.63 C CPU while the ramp model predicts
82.75 C; at180 min81.88 versus84.72 C. Compare these to five-minute CPU
medians centered on the stated times, only if the same run/load persists;
do not refit and call the changed prediction a successful forecast. These
are model-discrimination hypotheses, not safe temperature ceilings or
control settings. At17:51 UTC the original run2ba8b0226ea4 was active at
98.3 min, CPU81.75 C and hottest TT85.8 C; fresh telemetry, no run/recorder
error. The90 C guards and8-hour timeout remain unchanged.

Practical conclusion: strong shared-sink warming, now near heat balance
under the stated assumptions. Slowly warming room/inlet air is a good
candidate for the late drift, not a demonstrated exclusive cause. A warm
quasi-steady loop and room soak can coexist. Need actual inlet-air history
to discriminate them; do not label SYSTIN41 C as measured room temperature.

## CPU bursts: local junction-to-water rise on top of the shared sink

For a short burst the bulk water is approximately fixed. At100 W, one second
adds100 J, enough to raise3–4 litres by only0.006–0.008 C even with zero
radiator rejection. A many-degree CPU jump on that timescale is therefore
local, not the bulk water warming. The observed earlier pulse rose54.125→
91.25 C in about one sample; that37.125 C is a rise from the previous CPU
reading, NOT a measured CPU-to-water difference. Its one-second package
power average cannot identify a peak junction-to-water thermal resistance.

Once local transients have settled, the useful relation is
`T_CPU - T_water ≈ P_CPU * R_CPU_water`, with resistance in K/W. Illustratively,
100 W and0.25–0.30 K/W give25–30 C. That is physically plausible, not a
calibrated value for this CPU. A material layer contributes roughly L/(k*A),
and a convection boundary1/(h*A); heat spreading and the different die,
heat-spreader, block and wetted areas matter. Package watts and a hotspot
sensor are not necessarily represented by one invariant resistance across
different workloads. Idle CPU temperature is not water temperature either.

In the idealized near-steady model, CPU headroom is consumed by three terms:
`T_CPU ≈ T_inlet_air + Q_loop/H_radiator + P_CPU*R_CPU_water`.
Increasing the shared loop temperature shifts the CPU baseline up before a
burst adds its local rise. The native90 C guard remains in place for the
current experiment; no additional CPU burst was launched.

## Water inventory constraint and direct-to-air heat

User estimates less than 3 litres of coolant. Using water density about
1 kg/litre and specific heat about 4180 J/(kg K), water heat capacity is
less than roughly 12,540 J/K. This is not a bound on the entire loop's
effective capacity: radiator, blocks, tubing and other participating masses
also store heat. Coolant composition and temperature affect the estimate.

For exactly 3 litres, hypothetical 500 W deposited into coolant would give
2.39 C/min with zero rejection, or 1.20 C/min if 250 W is already rejected.
Those slopes are not upper bounds for all volumes below 3 litres; smaller
water volume heats faster at equal net power. The 500 W is an illustration,
not a measurement of heat entering the liquid or a sum of uncertain board
and chip-rail electrical readings.

If actual coolant warming were 0.02 C/min, less than 3 litres would store
less than about 4.2 W in the water itself. This would imply near balance
between inflow and radiator rejection ONLY if storage elsewhere were small
and heat inflow were known. CPU temperature slope is not a water-temperature
measurement. Small water volume alone cannot exclude an hour-long tail:
for the single lump with constant air, tau=C_effective/UA and net heating
approaches zero near equilibrium. Room heating and recirculation remain
plausible, not identified from the available sensors.

"At least 50% dumped into the radiator" must distinguish two fractions:
electrical heat captured by the liquid versus already-rejected heat divided
by liquid heat input. Neither fraction is measured here. The room-state RC
solver now accepts optional `room_heat_w`, an additional source bypassing
the liquid path. If P is a valid heat input, partition it as f*P through the
modeled coolant path and (1-f)*P directly to room air; do not count P twice.
This is a lumped heat-allocation approximation, not a model of device-to-air
resistance or local exhaust recirculation. The room equation becomes:

```
C_room dA/dt = H (W-A) + Q_direct_air - H_room (A-A_out)
```

At steady state all heat still reaches the room: changing the coolant
capture fraction changes coolant-to-room delta-T, but not total room heat
when total heat input is held fixed. Tests verify both heat routes and reject
unusable room-heat inputs. No experimental load or cooling setting changed.

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
