# Quietbox4: thermal model and what the experiment identifies

## Finding

The TT-only load strongly heated the CPU's shared cooling environment. CPU
Tctl rose from an original idle reference of 54.25 C to 82.125 C while CPU
package power changed only from about 18.83 to 20.79 W. After stopping TT,
CPU temperature returned to a 55.0 C median during minutes 35–45 off.
The four liquid-connected TT chips also cooled substantially. This is strong
evidence of shared-sink heat soak, not merely a CPU self-heating transient.

**A predictive temperature model is now available, but absolute coolant
temperature and the room-versus-internal contribution to the slow tail are
not identified.** A good temperature prediction is not a water thermometer.
There is no calibrated probability such as “90% certain” from this experiment.

The load remains stopped. Run `2ba8b0226ea4` ended at 2026-09-10 18:06:53 UTC
after 113.45 minutes at the user's request. The native approximately 1 Hz
recorder and NAS ClickHouse/Grafana collector continue. No load, reset,
clock change, fan adjustment or physical cooling modification was made for
the following analysis.

## Physical model

For each device i, shared liquid state W, and an optional room/inlet state A:

```text
C_i * dT_i/dt = Q_i - G_i * (T_i - W)
C_w * dW/dt   = sum_i[G_i * (T_i - W)] - H * (W - A)
C_a * dA/dt   = H * (W - A) + Q_direct_air - L * (A - A_reference)
observed_i   = T_i + sensor_offset_i
```

All capacities are positive J/K and conductances positive W/K. If inlet air
is measured, use it as the boundary and omit the last differential equation.
`tt_max/thermal_rc.py` implements exact piecewise-constant-input integration
with actual sample intervals. Internal heat transfers cancel, and constant
heat approaches an energy-balanced equilibrium. Tests cover these properties.

`Q_i` means heat deposited into the modeled device/liquid path. It is not
automatically the reported chip-rail or board-input wattage. If electrical
power P is partitioned into f*P through the liquid and (1-f)*P directly into
air, do not count the full P in both paths. Motherboard DIMMs and PSU losses
are additional domains, not deductions from CPU package or TT chip rails.
This minimal model omits separate block/radiator metal states, local air
paths, transport delays, flow dependence and nonlinear hotspot behavior.

At local equilibrium, a device's self-heating rise is approximately Q_i/G_i.
Consequently CPU-minus-TT differences suppress the common liquid temperature
and emphasize differing local loads and thermal resistances. A rapid TT
temperature drop on shutdown is not an equally rapid fall of all coolant.

## Data-calibrated input/output model

For low-host-power TT operation, an effective model can predict the CPU
cross-heating response without claiming that its states are literal water
or room temperatures:

```text
tau_j * dz_j/dt = (P_proxy - P_reference) - z_j
T_CPU(t) = T_reference
           + sum_j[initial_amplitude_j * exp(-(t-t0)/tau_j)]
           + sum_j[gain_j * z_j(t)]
```

`tt_max/thermal_modes.py` supports one or two positive-gain modes. Poles are
selected using only a chronological training prefix, and initial amplitudes
are free. A measured independent steady reference can be fixed explicitly;
otherwise the temperature reference is fitted. Exact zero-order-hold inputs
prevent future power leaking backward across a load change. Unit tests also
verify that changing later temperatures cannot change fitted parameters.

The main run is included after its first 60 seconds of setup, followed by
cooldown. Training ends five minutes after shutdown. Ten-second bins use
mean electrical power and median CPU temperature, requiring at least five
source samples. Samples with CPU package >=23 W or TT age >3 seconds are
excluded; four source samples were excluded in the main modeling interval.
This is not a model validated for CPU stress bursts or other workloads.

### Why the idle reference matters

Leaving the zero-power temperature unconstrained produced apparently good
training fits but very poor cooldown predictions: adding a second mode alone
did not solve this. Some fitted reference temperatures were below zero C.
These are extrapolated intercepts, not evidence of cold water.

The alternate scenario fixes the original idle CPU reference at 54.25 C and
uses the corresponding measured idle power for each electrical proxy. This
adds genuinely measured baseline information, **but assumes comparable air
and host thermal conditions**. The original reference lasted 74 seconds and
had a small residual CPU slope (-0.033 C/min); it is not perfect equilibrium.
TT idle clocks and powers also differ after the test, so measured power must
remain an input rather than assuming the old idle wattage has returned.

All three power proxies below are retained. Same-board INPUT_POWER readings
disagree; a minimum or mean across duplicated chip reports is not an
independently calibrated board power measurement. Better prediction with
one proxy does not prove that it is the physically correct reading.

| Electrical proxy | Modes | RMSE, 5–35 min off | RMSE, unused 35–45 min off |
| --- | ---: | ---: | ---: |
| Sum of chip rails | 1 | 1.795 C | 1.648 C |
| Sum of chip rails | 2 | 0.595 C | 1.655 C |
| Sum of each board's minimum report | 1 | 0.496 C | 0.169 C |
| Sum of each board's minimum report | 2 | 0.385 C | 0.220 C |
| Sum of each board's mean report | 1 | 1.337 C | 1.368 C |
| Sum of each board's mean report | 2 | 0.967 C | 1.939 C |

Model and reference choices had been evaluated on the earlier interval.
The final 35–45-minute interval was not read until the six fixed-reference
models and evaluation protocol were saved. No coefficients or poles were
refitted on that interval. These are predictions conditioned on measured
power, not unconditional forecasts of an unknown future workload. Reporting
all six results avoids selecting a favorable result after seeing that tail.

For illustration, the single-mode board-minimum model has tau 372.8 seconds
(6.21 minutes), gain 0.03850 C per proxy watt, reference power 230.12 W and
reference CPU temperature 54.25 C. The two-mode version has taus 328.7 and
1158.7 seconds, gains 0.03803 and 0.000958 C per proxy watt, and free initial
amplitudes +8.65 and -3.26 C. Those modal amplitudes are not physical water
or room temperatures. The extra mode improves the earlier interval but not
the final one; there is no robust identification of a second physical body.

An important power-reading confound also appears in the heating tail. From
minutes 40–45 to 85–90, the summed board-minimum mean rises 905.73→937.09 W,
while the mean-of-duplicates rises only 1057.47→1067.60 W. About 21.23 W of
the minimum's 31.36 W rise comes from a narrowing disagreement between the
paired reports, not from their midpoint increasing. Over minutes 40–90,
the board-minimum model reproduces a 0.0286 C/min CPU slope versus the
observed 0.0295 C/min, but that agreement cannot establish that a real power
increase caused the tail. A changing spread between noisy reports can change
their minimum. No proxy is promoted to calibrated heat based on fit quality.

Artifacts, with source queries, data bins and parameters:

- `thermal-analysis/20260910-q4-cooldown.json`: original idle and first 25 min off.
- `thermal-analysis/20260910-q4-modal-check.json`: 885 bins, training definitions,
  free-reference comparisons, fixed-reference models and late-check protocol.
- `thermal-analysis/20260910-q4-modal-late-evaluation.json`: 60 additional bins
  and errors for every fixed-reference model, without refitting.

These offline analysis modules do not change the running telemetry service
or its temperature guards. Tests validate the solver and fitting procedure;
the reported data checks validate only the limited operating regime above.

## Heat capacity and late heat balance

The user's estimate of 3–4 L water implies about 12.5–16.7 kJ/K. The stated
30 lb whole-machine estimate gives a metal-rich whole-box scenario around
17–26 kJ/K. The manufacturer's stock-system weight is instead 20 kg / 44 lb;
that alternative gives roughly 19–31 kJ/K under the same assumptions.
These are inventory scenarios, not measurements of participating loop mass.
See the [stock-system specifications](https://docs.tenstorrent.com/systems/quietbox/quietbox-bh-2/specifications.html)
and the calculation/source details in `THERMAL-NOTES.md`.

At the observed late rise of approximately 0.0278 C/min, a common-temperature
19–31 kJ/K body stores only about 9–14 W. If hundreds of watts are entering
that body, most are already being rejected. That supports a warm loop near
heat balance; it does not establish an exact steady state, coolant
temperature, or constant room air. A slowly warming inlet and a smaller
internal settling contribution can coexist with that heat balance.

## What remains unidentifiable

Two invariances are tested explicitly in the physical solver:

1. Shifting all physical temperatures and unmeasured air by the same amount,
   while subtracting that amount from unknown observation offsets, preserves
   the observed device trace. A calibrated temperature boundary would break
   this ambiguity; the unmatched original room reading is not such a trace.
2. Scaling deposited heat, every capacity and every conductance together
   preserves all temperatures. Uncalibrated electrical-to-water heat
   fractions therefore prevent extracting absolute capacity from fit gains
   alone. Independent mass information constrains, but does not calibrate,
   that mapping.

These invariances describe the stated model and unknowns, not a claim that
hardware sensors have arbitrary real errors. More generally, an unmeasured
inlet can be reconstructed differently for different assumed capacities,
conductances and heat fractions. A fitted slow pole cannot be labeled
“the room” merely because its time constant is long.

The missing discriminating evidence is a timestamped radiator-inlet air
measurement and a suitable coolant-temperature observation. A room sensor
helps, but may miss air warmed inside the case before it reaches the top
radiator. SYSTIN is retained as an additional hardware temperature, not
relabeled as measured ambient. A pump tachometer is not coolant flow.

**Current status:** model implementation and the limited predictive checks
are complete. The physical attribution of the slow tail and absolute water
temperature remain unverified; the overall identification goal stays open.
Do not restart a heat load just to collect more of the same uninstrumented
temperature curve. New boundary/coolant measurements are the next useful
input before planning another controlled experiment.
