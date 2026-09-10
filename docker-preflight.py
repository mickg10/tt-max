"""Read host prerequisites and prepare only the shared controller lock file."""
import os
from pathlib import Path
import stat

for required in ("/opt/tenstorrent/venv/bin/python", "/opt/tenstorrent/sfpi", "/dev/tenstorrent"):
    if not Path(required).exists():
        raise SystemExit(f"Missing host prerequisite: {required}")
python = Path("/opt/tenstorrent/venv/bin/python").resolve()
if not str(python).startswith(("/opt/tenstorrent/", "/usr/bin/")):
    raise SystemExit(f"Host interpreter points outside mounted runtime: {python}")
try:
    fd = os.open("/tmp/tt-max.run.lock", os.O_RDONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    os.fchmod(fd, 0o644)
except FileExistsError:
    fd = os.open("/tmp/tt-max.run.lock", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
try:
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        raise SystemExit("Controller lock is not a regular file")
finally:
    os.close(fd)
print("Host runtime and shared lock ready. This did not stop services or start benchmarks.")
