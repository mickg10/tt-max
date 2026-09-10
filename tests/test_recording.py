import pytest
import time
import threading
from tt_max.recording import Recorder, HostSensors, temperature_deltas


def test_history_persistence_and_cursor(tmp_path):
    path = tmp_path / 'telemetry.sqlite3'
    db = Recorder(path)
    db.record({'timestamp': 1, 'cpu_temperature_c': 60}, None)
    db.record({'timestamp': 2, 'cpu_temperature_c': 65}, {'id': 'test', 'state': 'running'})
    first = Recorder(path).history(limit=1)
    assert first['samples'][0]['cpu_temperature_c'] == 60
    second = db.history(after=first['next_after'])
    assert second['samples'][0]['run']['id'] == 'test'
    assert db.history(after=second['next_after'])['samples'] == []
    with pytest.raises(ValueError):
        db.history(limit=3601)


def test_power_wrap_and_missing_counter(tmp_path):
    domain = tmp_path / 'intel-rapl:0'
    domain.mkdir()
    (domain / 'name').write_text('package-0')
    (domain / 'max_energy_range_uj').write_text('100000000')
    (domain / 'energy_uj').write_text('90000000')
    reader = HostSensors(hwmon=tmp_path / 'none', powercap=tmp_path)
    assert reader.sample(10)['power_domains'][0]['watts'] is None
    (domain / 'energy_uj').write_text('10000000')
    assert reader.sample(11)['power_domains'][0]['watts'] == 20
    (domain / 'energy_uj').unlink()
    assert reader.sample(12)['power_domains'][0]['watts'] is None


def test_cpu_tt_deltas():
    assert temperature_deltas(70, {'devices': [{'id': 0, 'temperature_c': 50}, {'id': 1, 'temperature_c': None}]}) == {'0': 20}
    assert temperature_deltas(None, {}) == {}


def test_recorder_keeps_sampling_while_tt_poll_stalls(monkeypatch, tmp_path):
    from tt_max.engine import Engine
    release = threading.Event()
    def delayed_tt():
        release.wait(5)
        return {'devices': [], 'error': 'test unavailable'}
    monkeypatch.setattr('tt_max.engine.tt_snapshot', delayed_tt)
    engine = Engine()
    try:
        deadline = time.monotonic() + 4
        rows = []
        while time.monotonic() < deadline:
            rows = engine.recorder.history()['samples']
            if len(rows) >= 3:
                break
            time.sleep(.05)
        assert len(rows) >= 3
        assert rows[-1]['timestamp'] - rows[0]['timestamp'] < 3
        assert all(row['run'] is None for row in rows)
    finally:
        release.set()
        engine.close()
