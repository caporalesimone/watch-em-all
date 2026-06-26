#!/bin/sh
# App image dispatcher: one image, role chosen by the command (web | worker).
# web runs the real FastAPI app (1.B2); worker runs the dispatcher (src/worker, 4.B1).
set -eu

case "${1:-}" in
  web)
    exec python -m uvicorn src.web.app:app --host 0.0.0.0 --port "${WEA_PORT:-8080}"
    ;;
  worker)
    exec python -m src.worker
    ;;
  *)
    echo "usage: <image> {web|worker}" >&2
    exit 64
    ;;
esac
