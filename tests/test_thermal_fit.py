import numpy as np
import pytest
from tt_max.thermal_fit import design, fit


def test_measured_power_fit_predicts_heldout_step():
    t = np.arange(0, 1500, 10)
    power = np.where(t < 250, 100, np.where(t < 700, 400, 200))
    cpu = design(t, power, 180) @ np.array([40, 5, .08])
    result = fit(t, power, cpu, t < 900)
    assert result['tau_seconds'] == pytest.approx(180, rel=.02)
    assert result['gain_c_per_chip_rail_w'] == pytest.approx(.08, rel=.02)
    assert result['heldout_rmse_c'] < .1
