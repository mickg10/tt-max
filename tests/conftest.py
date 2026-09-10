import pytest


@pytest.fixture(autouse=True)
def isolated_telemetry_database(monkeypatch, tmp_path):
    monkeypatch.setenv('TT_MAX_DB', str(tmp_path / 'samples.sqlite3'))
