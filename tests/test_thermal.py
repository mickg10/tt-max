import numpy as np
import pytest

from tt_max.thermal import fit_cooldown


def test_recovers_common_decay_without_forcing_initial_equilibrium():
    t = np.arange(0, 900, 10)
    y = np.array([54, 39, 40]) + np.exp(-t[:, None] / 180) * [8, 6, 7]
    result = fit_cooldown(t, y)
    assert result['tau_seconds'] == pytest.approx(180, rel=.02)
    assert result['floor_c'] == pytest.approx([54, 39, 40], abs=.1)
    assert max(result['rmse_c']) < .05


def test_rejects_nonmonotonic_data():
    with pytest.raises(ValueError, match='time ordered'):
        fit_cooldown([0] * 10, np.ones((10, 2)))
