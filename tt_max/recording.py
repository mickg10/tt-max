"""Persistent one-second telemetry; independent from bounded run reports."""
import json
import math
import sqlite3
from contextlib import closing
from pathlib import Path


class Recorder:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS samples (id INTEGER PRIMARY KEY, timestamp REAL NOT NULL, run_id TEXT, payload TEXT NOT NULL)')
            db.execute('CREATE INDEX IF NOT EXISTS samples_timestamp ON samples(timestamp)')

    def record(self, sample, run):
        payload = dict(sample, run=run, schema_version=1)
        with closing(sqlite3.connect(self.path, timeout=2)) as db, db:
            db.execute('INSERT INTO samples(timestamp,run_id,payload) VALUES(?,?,?)',
                       (sample['timestamp'], run.get('id') if run else None, json.dumps(payload, allow_nan=False)))

    def history(self, after=0, limit=1000):
        after, limit = int(after), int(limit)
        if not 0 <= after < 2**63 or not 1 <= limit <= 3600:
            raise ValueError('after must be nonnegative; limit must be 1–3600')
        with closing(sqlite3.connect(self.path, timeout=2)) as db:
            rows = db.execute('SELECT id,payload FROM samples WHERE id>? ORDER BY id LIMIT ?', (after, limit)).fetchall()
        return {'samples': [dict(json.loads(payload), sample_id=i) for i, payload in rows],
                'next_after': rows[-1][0] if rows else after}


def read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


class HostSensors:
    def __init__(self, hwmon='/sys/class/hwmon', powercap='/sys/class/powercap'):
        self.hwmon, self.powercap = Path(hwmon), Path(powercap)
        self.previous = {}

    def sample(self, now):
        sensors, domains = [], []
        for hw in self.hwmon.glob('hwmon*'):
            name = read(hw / 'name')
            if name not in ('nct6799', 'nct6775', 'nct6776', 'nct6796', 'k10temp', 'coretemp', 'blackhole', 'wormhole'):
                continue
            values = {}
            for pattern in ('temp*_input', 'temp*_label', 'fan*_input', 'pwm[0-9]', 'pwm*_enable'):
                for field in hw.glob(pattern):
                    values[field.name] = read(field)
            sensors.append({'name': name, 'path': str(hw.resolve()), 'raw': values})
        for domain in self.powercap.glob('intel-rapl:*'):
            raw, limit = read(domain / 'energy_uj'), read(domain / 'max_energy_range_uj')
            watts = None
            if raw is not None and limit is not None:
                energy, maximum = int(raw), int(limit)
                old = self.previous.get(str(domain))
                if old and now > old[1] and maximum > 0:
                    watts = ((energy - old[0]) % maximum) / 1e6 / (now - old[1])
                self.previous[str(domain)] = (energy, now)
            domains.append({'name': read(domain / 'name'), 'path': str(domain), 'watts': watts,
                            'energy_uj': int(raw) if raw is not None else None,
                            'error': 'unreadable energy counter' if raw is None else None})
        return {'hwmon': sensors, 'power_domains': domains, 'sampled_monotonic': now}


def temperature_deltas(cpu, tt):
    if cpu is None or not math.isfinite(cpu):
        return {}
    return {str(d['id']): cpu - d['temperature_c'] for d in tt.get('devices', [])
            if isinstance(d.get('temperature_c'), (float, int)) and math.isfinite(d['temperature_c'])}
