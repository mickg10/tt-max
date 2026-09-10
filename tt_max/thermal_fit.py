"""Conditional CPU cross-heating fit from a low-host-power TT soak.

Fits tau*dT/dt = -T + floor + gain*TT_chip_rail_w. Initial temperature
is free. This is an effective input/output model, not absolute coolant
thermometry. Changing ambient and CPU heat must be checked separately.
"""
import argparse
import json
import sqlite3
from contextlib import closing

import numpy as np


def design(t, power, tau):
    filtered = np.zeros(len(t))
    for k, dt in enumerate(np.diff(t)):
        decay = np.exp(-dt / tau)
        filtered[k + 1] = decay * filtered[k] + (1 - decay) * power[k]
    return np.column_stack((np.ones(len(t)), np.exp(-(t-t[0])/tau), filtered))


def fit(t, power, cpu, train):
    candidates = []
    for tau in np.geomspace(10, 5000, 600):
        x = design(t, power, tau)
        coefficients = np.linalg.lstsq(x[train], cpu[train], rcond=None)[0]
        if coefficients[2] < 0:
            continue
        prediction = x @ coefficients
        mse = np.mean((prediction[train]-cpu[train])**2)
        candidates.append((mse, tau, coefficients, prediction))
    if not candidates:
        raise ValueError('No positive cross gain fitted')
    mse, tau, coef, prediction = min(candidates, key=lambda v:v[0])
    return {'tau_seconds': float(tau), 'gain_c_per_chip_rail_w': float(coef[2]),
            'extrapolated_zero_TT_power_cpu_floor_c': float(coef[0]),
            'training_rmse_c': float(np.sqrt(mse)),
            'heldout_rmse_c': float(np.sqrt(np.mean((prediction[~train]-cpu[~train])**2))) if (~train).any() else None,
            'warning': 'Conditional fit: no measured ambient; electrical proxy is not calibrated deposited heat; floor is extrapolated, not coolant temperature'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('database'); p.add_argument('run_id')
    p.add_argument('--train-seconds', type=float, default=300)
    args = p.parse_args()
    with closing(sqlite3.connect(f'file:{args.database}?mode=ro', uri=True)) as db:
        rows = [json.loads(x) for x, in db.execute('SELECT payload FROM samples WHERE run_id=? ORDER BY timestamp', (args.run_id,))]
    bins = {}
    for row in rows:
        elapsed = row['timestamp']-row['run']['started_at']
        if elapsed < 60 or row.get('tt_age_seconds') is None or row['tt_age_seconds'] > 3:
            continue
        if row['run']['state'] != 'running':
            continue
        devices = row['tt']['devices']
        if len(devices) != 4:
            continue
        cpu_power = next((v['watts'] for v in row['host_sensors']['power_domains'] if v['name']=='package-0'), None)
        values = [elapsed, sum(d['power_w'] for d in devices), row['cpu_temperature_c'], cpu_power]
        if any(v is None for v in values) or not np.isfinite(values).all():
            continue
        bins.setdefault(int(elapsed//10), []).append(values)
    # Mean power preserves energy; median temperature reduces short host bursts.
    data = []
    for _, values in sorted(bins.items()):
        a = np.asarray(values)
        if len(a) < 5:
            continue
        data.append([a[:,0].mean(), a[:,1].mean(), np.median(a[:,2]), a[:,3].mean()])
    a = np.asarray(data)
    if len(a) < 15:
        raise ValueError('Need at least 15 usable ten-second bins')
    train = a[:,0] < args.train_seconds
    if train.sum() < 10:
        raise ValueError('Insufficient training interval')
    print(json.dumps({'samples':len(a), 'duration_seconds':float(a[-1,0]),
        'cpu_power_range_w':[float(a[:,3].min()),float(a[:,3].max())],
        'holdout_fit':fit(a[:,0],a[:,1],a[:,2],train),
        'whole_trace_fit':fit(a[:,0],a[:,1],a[:,2],np.ones(len(a),dtype=bool))}, indent=2))


if __name__ == '__main__':
    main()
