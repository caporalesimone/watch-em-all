#!/bin/sh
# Phase 0 stub dispatcher: one image, role chosen by the command (web | worker).
# The real app (1.B2 / 4.B1) keeps the same contract: `web` serves the API + SPA,
# `worker` runs the dispatcher/runner loop.
set -eu

case "${1:-}" in
  web)
    exec python /app/stub/server.py
    ;;
  worker)
    exec python /app/stub/worker.py
    ;;
  *)
    echo "usage: <image> {web|worker}" >&2
    exit 64
    ;;
esac
