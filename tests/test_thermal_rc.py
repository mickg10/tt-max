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
