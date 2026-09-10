"""Root-only service pre-start: grant one service group read access to RAPL."""
import grp
import os
from pathlib import Path
import stat
import sys

if os.geteuid() != 0:
    raise SystemExit('Run as root with the service group as the sole argument')
gid = grp.getgrnam(sys.argv[1]).gr_gid
for domain in Path('/sys/class/powercap').glob('intel-rapl:*'):
    counter = domain / 'energy_uj'
    if counter.exists():
        os.chown(counter, -1, gid)
        os.chmod(counter, stat.S_IMODE(counter.stat().st_mode) | stat.S_IRGRP)
