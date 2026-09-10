"""Descriptive cooldown fit; does not establish a shared physical coolant node."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def fit_cooldown(seconds, temperatures):
    """Fit independent floors/amplitudes with one common exponential timescale.

    This is a descriptive model only: correlated cooling from separate masses
    can produce the same result. Input must be a passive, comparable-power tail.
    """
    t = np.asarray(seconds, dtype=float)
    y = np.asarray(temperatures, dtype=float)
    if t.ndim != 1 or y.ndim != 2 or len(t) != len(y) or len(t) < 10:
        raise ValueError("Need at least ten aligned samples and a temperature matrix")
    if not np.isfinite(t).all() or not np.isfinite(y).all() or np.any(np.diff(t) <= 0):
        raise ValueError("Samples must be finite and strictly time ordered")
    t = t - t[0]
    candidates = []
    for tau in np.geomspace(5, max(600, 10 * t[-1]), 500):
        design = np.column_stack((np.ones(len(t)), np.exp(-t / tau)))
        coef = np.linalg.lstsq(design, y, rcond=None)[0]
        if np.any(coef[1] < 0):
            continue
        error = np.mean((design @ coef - y) ** 2, axis=0)
        candidates.append((float(error.mean()), float(tau), coef, error))
    if not candidates:
        raise ValueError("No nonnegative-amplitude cooling fit")
    _, tau, coef, error = min(candidates, key=lambda c: c[0])
    return {"tau_seconds": tau, "floor_c": coef[0].tolist(),
            "initial_excess_c": coef[1].tolist(), "rmse_c": np.sqrt(error).tolist(),
            "warning": "Descriptive common decay, not proof of shared coolant or a confidence interval"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path, help="Passive collector JSONL")
    parser.add_argument("--skip-seconds", type=float, default=30)
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.trace.read_text().splitlines() if line.strip()]
    start = rows[0]["timestamp"]
    # Ten-second medians reduce CPU sampling bursts; no interpolation across gaps.
    bins = {}
    for row in rows:
        if row.get("dashboard", {}).get("running"):
            raise ValueError("Trace includes active load; select a passive tail first")
        seconds = row["timestamp"] - start
        if seconds < args.skip_seconds:
            continue
        sensors = row["sensors"]
        cpu = next(float(s["values"]["temp1_input"]) / 1000
                   for s in sensors.values() if s["name"] == "k10temp")
        chips = sorted((path, float(s["values"]["temp1_input"]) / 1000)
                       for path, s in sensors.items() if s["name"] == "blackhole")
        bins.setdefault(int(seconds // 10), []).append([seconds, cpu, *[v for _, v in chips]])
    medians = np.array([np.median(values, axis=0) for _, values in sorted(bins.items())])
    result = fit_cooldown(medians[:, 0], medians[:, 1:])
    result["channels"] = ["CPU Tctl", *[path for path, _ in chips]]
    result["binned_samples"] = len(medians)
    result["duration_seconds"] = float(medians[-1, 0] - medians[0, 0])
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
