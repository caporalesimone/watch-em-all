#!/usr/bin/env bash
# Tolerant post-create: the toolchain files arrive with later MVPs
# (pyproject.toml with 1.B1, src/frontend/package.json with 1.F1).
# Each install activates by itself once its file exists.
set -e

if [ -f pyproject.toml ]; then
    poetry install
else
    echo "post-create: no pyproject.toml yet (arrives with 1.B1) - skipping poetry install"
fi

if [ -f src/frontend/package.json ]; then
    (cd src/frontend && npm install)
else
    echo "post-create: no src/frontend/package.json yet (arrives with 1.F1) - skipping npm install"
fi
