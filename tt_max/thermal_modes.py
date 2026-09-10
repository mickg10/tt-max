"""Positive, causal electrical-power-to-temperature modal model.

Each mode obeys tau * dx/dt = power - x; temperature is a free reference
plus a nonnegative sum of these filtered inputs and decaying initial states.
This is an input/output model, NOT identification of water/room temperatures,
deposited heat, physical heat capacity, or an exact radiator time constant.
"""
from itertools import combinations

import numpy as np


def design(times, power, taus):
    """Exact zero-order hold; power[k] drives interval k, never earlier ones."""
    t, p, tau = (np.asarray(v, dtype=float) for v in (times, power, taus))
    if t.ndim != 1 or len(t) < 2 or p.shape != t.shape:
        raise ValueError("Need aligned one-dimensional times and power")
    if tau.ndim != 1 or not len(tau) or np.any(tau <= 0):
        raise ValueError("Time constants must be a nonempty positive vector")
    if not all(np.isfinite(v).all() for v in (t, p, tau)):
        raise ValueError("Inputs must be finite")
    if np.any(np.diff(t) <= 0):
        raise ValueError("Times must increase strictly")
    filtered = np.zeros((len(t), len(tau)))
    for k, dt in enumerate(np.diff(t)):
        decay = np.exp(-dt / tau)
        filtered[k + 1] = decay * filtered[k] - np.expm1(-dt / tau) * p[k]
    return np.column_stack((np.ones(len(t)),
                            np.exp(-(t - t[0])[:, None] / tau), filtered))


def _positive_gains(x, y, modes, fixed_reference=None):
    """Enumerate active gain constraints; offsets/initial states remain free."""
    free = list(range(0 if fixed_reference is None else 1, modes + 1))
    target = y if fixed_reference is None else y - fixed_reference
    gain_columns = list(range(modes + 1, 2 * modes + 1))
    candidates = []
    for count in range(modes + 1):
        for active in combinations(gain_columns, count):
            columns = free + list(active)
            coef = np.zeros(x.shape[1])
            coef[columns] = np.linalg.lstsq(x[:, columns], target, rcond=None)[0]
            if fixed_reference is not None:
                coef[0] = fixed_reference
            if np.any(coef[gain_columns] < 0):
                continue
            candidates.append((float(np.mean((x @ coef - y) ** 2)), coef))
    return min(candidates, key=lambda item: item[0])


def fit(times, power, temperature, train_end_seconds, tau_grid, modes=2,
        minimum_tau_ratio=2.0, steady_reference=None):
    """Select poles on a chronological training prefix only.

    train_end_seconds uses the same coordinate as times. Held-out measured
    power is an allowed input; held-out temperature is used only for scoring.
    The resulting check is input-conditioned prediction, not an unconditional
    forecast of an unknown future workload. No physical states are inferred.
    Optional steady_reference=(power, temperature) fixes an independently
    supplied steady equilibrium. Use it only as an explicit assumption when
    ambient or unmodeled host activity differs from the reference interval.
    """
    t, p, y, grid = (np.asarray(v, dtype=float)
                     for v in (times, power, temperature, tau_grid))
    if modes not in (1, 2):
        raise ValueError("Only one or two modes are supported")
    if grid.ndim != 1 or len(grid) < modes or np.any(grid <= 0):
        raise ValueError("Need enough positive candidate time constants")
    if not np.isfinite(grid).all() or not np.isfinite(train_end_seconds):
        raise ValueError("Grid and split must be finite")
    if not np.isfinite(minimum_tau_ratio) or minimum_tau_ratio <= 1:
        raise ValueError("Minimum time-constant ratio must exceed one")
    # Also validates causal-input dimensions and timestamps before indexing.
    design(t, p, [grid[0]])
    if y.shape != t.shape or not np.isfinite(y).all():
        raise ValueError("Temperature must be aligned and finite")
    reference_power, reference_temperature = 0.0, None
    if steady_reference is not None:
        reference = np.asarray(steady_reference, dtype=float)
        if reference.shape != (2,) or not np.isfinite(reference).all():
            raise ValueError("Steady reference must be a finite power/temperature pair")
        reference_power, reference_temperature = reference.tolist()
        p = p - reference_power
    train = t < train_end_seconds
    if train.sum() < max(10, 2 * (2 * modes + 1)):
        raise ValueError("Insufficient training prefix")
    candidates = []
    unique_grid = sorted(set(grid.tolist()))
    # Filter every candidate pole once; reuse columns for each pole pair.
    all_columns = design(t, p, unique_grid)
    for indices in combinations(range(len(unique_grid)), modes):
        taus = tuple(unique_grid[i] for i in indices)
        if modes == 2 and taus[1] / taus[0] < minimum_tau_ratio:
            continue
        columns = ([0] + [1 + i for i in indices]
                   + [1 + len(unique_grid) + i for i in indices])
        x = all_columns[:, columns]
        mse, coef = _positive_gains(x[train], y[train], modes, reference_temperature)
        candidates.append((mse, taus, coef))
    if not candidates:
        raise ValueError("No admissible time-constant candidates")
    mse, taus, coef = min(candidates, key=lambda item: item[0])
    x = design(t, p, taus)
    prediction = x @ coef
    norms = np.linalg.norm(x[train], axis=0)
    scaled = x[train] / np.where(norms > 0, norms, 1)
    raw_condition, scaled_condition = (float(np.linalg.cond(v))
                                       for v in (x[train], scaled))
    return {
        "tau_seconds": list(taus),
        "reference_c": float(coef[0]),
        "reference_power_w": reference_power,
        "reference_was_fixed": steady_reference is not None,
        "initial_amplitude_c": coef[1:modes + 1].tolist(),
        "gain_c_per_proxy_w": coef[modes + 1:].tolist(),
        "training_rmse_c": float(np.sqrt(mse)),
        "later_rmse_c": (float(np.sqrt(np.mean((prediction[~train] - y[~train]) ** 2)))
                         if (~train).any() else None),
        "training_samples": int(train.sum()),
        "later_samples": int((~train).sum()),
        "tau_at_search_boundary": [tau in (unique_grid[0], unique_grid[-1])
                                   for tau in taus],
        "zero_gain_modes": [i for i, gain in enumerate(coef[modes + 1:])
                            if gain == 0],
        "rank_deficient_training_design": bool(np.linalg.matrix_rank(scaled) < x.shape[1]),
        "training_design_condition_number": (raw_condition if np.isfinite(raw_condition) else None),
        "column_normalized_condition_number": (scaled_condition if np.isfinite(scaled_condition) else None),
        "prediction_c": prediction.tolist(),
        "warning": "Electrical proxy and latent modes are not calibrated heat or identified physical water/room states",
    }
