"""Stub worker — phase 0 placeholder (worker role of the app image).

Declared mock, replaced by the real worker in 4.B1: it only touches the
heartbeat file and logs a tick every minute. The heartbeat file is the
same one the compose healthcheck watches (age < 180s, see deployment.md).
"""

import os
import time

HEARTBEAT_FILE = os.environ.get("HEARTBEAT_FILE", "/tmp/worker-heartbeat")
TICK_SECONDS = int(os.environ.get("TICK_SECONDS", "60"))

if __name__ == "__main__":
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
