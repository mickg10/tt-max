"""Passive thermal RC network, with an optional warming-room state.

Inputs are deposited heat, not uncalibrated electrical board readings. Neither
capacities nor absolute coolant temperature are identified merely by using
this model. Fit/calibrate these parameters against independent experiments.
"""
import numpy as np


def simulate(times, heat_w, air_c, capacities, block_conductances,
             radiator_conductance, initial_c, room_capacity=None,
             room_loss=None, room_heat_w=None):
    """Exact zero-order-hold simulation with actual sample intervals.

    State order: devices, shared sink, optional room. Without a room state,
    air_c is measured radiator inlet air. With one it is outside/reference air;
    radiator heat enters the room and room_loss conducts heat out of it.
    Capacities: one J/K value per device plus shared sink. Conductances: W/K.
    Heat has shape (time, devices); interval k uses heat_w[k] and air_c[k].
    Optional room_heat_w has shape (time,) and adds heat directly to the room,
    bypassing the modeled device-to-coolant path. For example, partition a
    measured electrical input P into heat_w=f*P and room_heat_w=(1-f)*P;
    do not add the full P again as room heat. Neither P nor f is inferred here.
    This additional path requires the room state; measured inlet air already
    acts as a boundary condition without it. It does not model local exhaust
    recirculation or an additional device-to-case-air thermal resistance.
    """
    t, q, air = map(lambda a: np.asarray(a, dtype=float), (times, heat_w, air_c))
    c = np.asarray(capacities, dtype=float)
    g = np.asarray(block_conductances, dtype=float)
    initial = np.asarray(initial_c, dtype=float)
    n = len(g)
    if t.ndim != 1 or len(t) < 2 or np.any(np.diff(t) <= 0):
        raise ValueError('Times must be strictly increasing')
    if q.shape != (len(t), n) or air.shape != t.shape or c.shape != (n + 1,):
        raise ValueError('Inconsistent input shapes')
    if np.any(c <= 0) or np.any(g <= 0) or radiator_conductance <= 0:
        raise ValueError('Capacities and conductances must be positive')
    room = room_capacity is not None
    if room and (room_capacity <= 0 or room_loss is None or room_loss <= 0):
        raise ValueError('Room capacity and heat loss must be positive')
    if room_heat_w is not None and not room:
        raise ValueError('Direct room heat requires a room state')
    room_heat = np.zeros_like(t) if room_heat_w is None else np.asarray(room_heat_w, dtype=float)
    if room_heat.shape != t.shape:
        raise ValueError('Room heat must have one value per time sample')
    if room:
        c = np.append(c, room_capacity)
    if initial.shape != c.shape:
        raise ValueError('Initial state shape mismatch')
    if not all(np.isfinite(a).all() for a in (t, q, air, c, g, initial, room_heat)):
        raise ValueError('Inputs must be finite')
    if not np.isfinite(radiator_conductance) or (room and not np.isfinite(room_loss)):
        raise ValueError('Conductances must be finite')
    # Symmetric conductance graph; internal heat transfers cancel exactly.
    loss = np.zeros((len(c), len(c)))
    def link(i, j, conductance):
        loss[i, i] += conductance; loss[j, j] += conductance
        loss[i, j] -= conductance; loss[j, i] -= conductance
    for i in range(n):
        link(i, n, g[i])
    if room:
        link(n, n + 1, radiator_conductance)
        loss[-1, -1] += room_loss
        boundary = room_loss
    else:
        loss[-1, -1] += radiator_conductance
        boundary = radiator_conductance
    root_c = np.sqrt(c)
    eig, vectors = np.linalg.eigh(loss / root_c[:, None] / root_c[None, :])
    result = np.empty((len(t), len(c)))
    result[0] = initial
    for k, dt in enumerate(np.diff(t)):
        source = np.zeros(len(c)); source[:n] = q[k]
        source[-1] += boundary * air[k]
        if room:
            source[-1] += room_heat[k]
        decay = np.exp(-eig * dt)
        gain = -np.expm1(-eig * dt) / eig
        state = vectors.T @ (root_c * result[k])
        forcing = vectors.T @ (source / root_c)
        result[k + 1] = (vectors @ (decay * state + gain * forcing)) / root_c
    return result
