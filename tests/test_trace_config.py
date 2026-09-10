import pytest
from tt_max.engine import normalize_config


def test_trace_opt_in_does_not_enable_host_stress():
    c = normalize_config(dict(tt_trace=True, tt=True, cpu_workers=0, memory_gb=0))
    assert c['tt_trace'] is True
    assert c['cpu_workers'] == 0 and c['memory_gb'] == 0
    assert normalize_config({})['tt_trace'] is False


@pytest.mark.parametrize('value', ['true', 1, None])
def test_trace_requires_boolean(value):
    with pytest.raises(ValueError, match='tt_trace'):
        normalize_config({'tt_trace': value})
