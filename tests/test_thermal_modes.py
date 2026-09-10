import numpy as np
import pytest

from tt_max.thermal_modes import design, fit


def example():
    t = np.arange(0, 2400, 10, dtype=float)
    p = np.where((t >= 150) & (t < 1100), 420.0, 65.0)
    coef = np.array([38.0, 3.0, -2.0, .035, .020])
    return t, p, design(t, p, [120, 700]) @ coef


def test_exact_two_mode_recovery_and_later_prediction():
    t, p, y = example()
    result = fit(t, p, y, 1400, [60, 120, 300, 700, 1500])
    assert result['tau_seconds'] == [120, 700]
    assert result['gain_c_per_proxy_w'] == pytest.approx([.035, .020])
    assert result['later_rmse_c'] < 1e-9


def test_later_temperatures_cannot_choose_parameters():
    t, p, y = example()
    first = fit(t, p, y, 1400, [60, 120, 300, 700])
    y[t >= 1400] += 25
    second = fit(t, p, y, 1400, [60, 120, 300, 700])
    for key in ('tau_seconds', 'reference_c', 'initial_amplitude_c',
                'gain_c_per_proxy_w', 'training_rmse_c', 'prediction_c'):
        assert first[key] == second[key]
    assert second['later_rmse_c'] == pytest.approx(25)


def test_power_does_not_leak_backwards_and_irregular_steps_are_exact():
    t = np.array([0., 3., 10., 40.])
    p = np.array([100., 100., 500., 900.])
    x = design(t, p, [10.])
    assert x[2, 2] == pytest.approx(100 * (1 - np.exp(-1)))
    p[2:] += 1000
    assert np.array_equal(design(t, p, [10.])[:3], x[:3])


def test_gains_remain_nonnegative():
    t, p, y = example()
    result = fit(t, p, -y, 1400, [60, 120, 300, 700])
    assert np.all(np.array(result['gain_c_per_proxy_w']) >= 0)


@pytest.mark.parametrize('times,power,taus', [
    ([0, 0], [1, 2], [10]),
    ([0, 1], [1], [10]),
    ([0, 1], [1, 2], [0]),
    ([0, 1], [1, float('nan')], [10]),
])
def test_rejects_bad_inputs(times, power, taus):
    with pytest.raises(ValueError):
        design(times, power, taus)


def test_rejects_nonfinite_split_or_inadequate_training():
    t, p, y = example()
    for split in (float('nan'), 50):
        with pytest.raises(ValueError):
            fit(t, p, y, split, [120, 700])


def test_single_mode_and_no_later_interval():
    t = np.arange(0, 1200, 10)
    p = np.where(t < 300, 300., 60.)
    y = design(t, p, [120]) @ np.array([40., 2., .1])
    result = fit(t, p, y, 1200, [60, 120, 300], modes=1)
    assert result['tau_seconds'] == [120]
    assert result['training_rmse_c'] < 1e-9
    assert result['later_rmse_c'] is None


def test_search_boundary_and_unidentified_zero_input_are_visible():
    t = np.arange(0, 1200, 10)
    p = np.zeros(len(t))
    y = 40 + 8 * np.exp(-t / 120)
    result = fit(t, p, y, 900, [120, 300], modes=1)
    assert result['tau_at_search_boundary'] == [True]
    assert result['zero_gain_modes'] == [0]
    assert result['rank_deficient_training_design']
    assert result['later_rmse_c'] < 1e-9


def test_independently_fixed_reference_is_respected():
    t, p, y = example()
    steady_temperature = 38 + 65 * (.035 + .020)
    result = fit(t, p, y, 1400, [60, 120, 300, 700],
                 steady_reference=[65, steady_temperature])
    assert result['reference_was_fixed']
    assert result['reference_power_w'] == 65
    assert result['reference_c'] == steady_temperature
    assert result['gain_c_per_proxy_w'] == pytest.approx([.035, .020])
    assert result['later_rmse_c'] < 1e-9
    with pytest.raises(ValueError):
        fit(t, p, y, 1400, [120, 700], steady_reference=[65, float('nan')])
