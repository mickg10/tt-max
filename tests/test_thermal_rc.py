import numpy as np
import pytest
from tt_max.thermal_rc import simulate


def test_constant_heat_reaches_energy_balance():
    t = np.arange(0, 10001, 10)
    out = simulate(t, np.full((len(t), 1), 100), np.full(len(t), 20),
                   [10, 100], [20], 10, [20, 20])
    assert out[-1] == pytest.approx([35, 30], abs=.001)
    assert np.all(np.diff(out[:, 1]) >= -1e-9)


def test_room_adds_temperature_rise_and_no_heat_preserves_equilibrium():
    t = np.arange(0, 20001, 10)
    out = simulate(t, np.full((len(t), 1), 100), np.full(len(t), 20),
                   [10, 100], [20], 10, [20, 20, 20], 1000, 5)
    assert out[-1] == pytest.approx([55, 50, 40], abs=.001)
    out = simulate(t, np.zeros((len(t), 1)), np.full(len(t), 20),
                   [10, 100], [20], 10, [20, 20])
    assert np.max(np.abs(out - 20)) < 1e-8


def test_rejects_negative_capacity():
    with pytest.raises(ValueError, match='positive'):
        simulate([0, 1], [[0], [0]], [20, 20], [-1, 100], [20], 10, [20, 20])


def test_direct_room_heat_preserves_total_power_without_double_counting():
    t = np.arange(0, 20001, 10)
    common = dict(times=t, air_c=np.full(len(t), 20), capacities=[10, 100],
                  block_conductances=[20], radiator_conductance=10,
                  initial_c=[20, 20, 20], room_capacity=1000, room_loss=5)
    all_water = simulate(heat_w=np.full((len(t), 1), 100), **common)
    half_water = simulate(heat_w=np.full((len(t), 1), 50),
                          room_heat_w=np.full(len(t), 50), **common)
    # Both cases deposit 100 W into the room eventually. Only half goes
    # through the water in the second case, reducing its radiator delta-T.
    assert all_water[-1] == pytest.approx([55, 50, 40], abs=.001)
    assert half_water[-1] == pytest.approx([47.5, 45, 40], abs=.001)


@pytest.mark.parametrize('room_heat', ([0], [0, float('nan')]))
def test_rejects_invalid_direct_room_heat(room_heat):
    with pytest.raises(ValueError):
        simulate([0, 1], [[0], [0]], [20, 20], [10, 100], [20], 10,
                 [20, 20, 20], room_capacity=1000, room_loss=5,
                 room_heat_w=room_heat)


def test_direct_room_heat_requires_room_state():
    with pytest.raises(ValueError, match='room state'):
        simulate([0, 1], [[0], [0]], [20, 20], [10, 100], [20], 10,
                 [20, 20], room_heat_w=[0, 0])
