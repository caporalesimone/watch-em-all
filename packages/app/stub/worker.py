"""Stub worker — phase 0 placeholder (worker role of the app image).

Declared mock, replaced by the real worker in 4.B1: it only touches the
heartbeat file and logs a tick every minute. The heartbeat file is the
same one the compose healthcheck watches (age < 180s, see deployment.md).

It runs as PID 1, so it installs a SIGTERM/SIGINT handler to exit promptly on
`docker stop` (PID 1 ignores signals that have no handler → otherwise Docker
waits the full stop timeout, ~10s, then SIGKILL).
"""

import os
import signal
import sys
import time
from types import FrameType

HEARTBEAT_FILE = os.environ.get("WEA_HEARTBEAT_FILE", "/tmp/worker-heartbeat")
TICK_SECONDS = int(os.environ.get("WEA_TICK_SECONDS", "60"))


def _shutdown(signum: int, _frame: FrameType | None) -> None:
    print(f"stub-worker: signal {signum} received, stopping", flush=True)
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    print(
        f"stub-worker: heartbeat on {HEARTBEAT_FILE} every {TICK_SECONDS}s "
        "— mock, replaced by 4.B1",
        flush=True,
    )
    while True:
        with open(HEARTBEAT_FILE, "w") as fh:
            fh.write(str(int(time.time())))
        print("stub-worker: tick", flush=True)
        time.sleep(TICK_SECONDS)
