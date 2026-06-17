#!/bin/sh
# App image dispatcher: one image, role chosen by the command (web | worker).
# web runs the real FastAPI app (1.B2); worker stays a stub until phase 4 (4.B1).
set -eu

case "${1:-}" in
  web)
    exec python -m uvicorn src.web.app:app --host 0.0.0.0 --port "${PORT:-8080}"
    ;;
  worker)
    exec python /app/stub/worker.py
    ;;
  *)
    echo "usage: <image> {web|worker}" >&2
    exit 64
    ;;
esac
