#!/usr/bin/env bash
# Restore (1.T3, INF-14/INF-16): verify the archive, refuse while web/worker are
# connected, confirm explicitly, then recreate the DB from the dump. The dump IS
# the state being brought back to life — the one legitimate exception to the
# no-drop rule (DB-R4). Bootstrap files in the archive are extracted to /backups
# for the operator (the live .env/config.yaml are mounted read-only).
#
#   docker compose stop web worker
#   docker compose run --rm ops restore.sh /backups/watchemall-backup-<date>.tar.gz
set -euo pipefail

export PGHOST="${PGHOST:-db}"
export PGUSER="${PGUSER:-${POSTGRES_USER:-watchemall}}"
export PGPASSWORD="${PGPASSWORD:-${POSTGRES_PASSWORD:-}}"
export PGDATABASE="${PGDATABASE:-${POSTGRES_DB:-watchemall}}"

archive="${1:-}"
if [ -z "$archive" ]; then
  echo "usage: restore.sh /backups/watchemall-backup-<date>.tar.gz" >&2
  exit 64
fi
if [ ! -f "$archive" ]; then
  echo "restore: archive not found: ${archive}" >&2
  exit 66
fi

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

# 1) Verify the archive is a readable tarball that contains the DB dump.
echo "restore: verifying archive…"
tar -tzf "$archive" >/dev/null
tar -xzf "$archive" -C "$workdir"
if [ ! -f "${workdir}/db.dump" ]; then
  echo "restore: db.dump missing from archive — not a Watch 'Em All backup" >&2
  exit 65
fi

# 2) Refuse if the app stack is still connected to the database (INF-14).
active="$(psql -tA -d postgres -c \
  "SELECT count(*) FROM pg_stat_activity WHERE datname = '${PGDATABASE}';" | tr -d '[:space:]')"
if [ "${active:-0}" -gt 0 ]; then
  echo "restore: ${active} connection(s) still open on '${PGDATABASE}'." >&2
  echo "restore: stop the app first:  docker compose stop web worker" >&2
  exit 1
fi

# 3) Explicit confirmation (skippable for automation with RESTORE_ASSUME_YES=1).
if [ "${RESTORE_ASSUME_YES:-}" != "1" ]; then
  echo "This will DROP and recreate database '${PGDATABASE}' from:"
  echo "  ${archive}"
  printf "Type 'yes' to continue: "
  read -r reply
  if [ "$reply" != "yes" ]; then
    echo "restore: aborted"
    exit 1
  fi
fi

# 4) Recreate the database and load the dump.
echo "restore: recreating database '${PGDATABASE}'…"
psql -d postgres -c "DROP DATABASE IF EXISTS \"${PGDATABASE}\";"
psql -d postgres -c "CREATE DATABASE \"${PGDATABASE}\" OWNER \"${PGUSER}\";"
pg_restore --dbname="${PGDATABASE}" --no-owner "${workdir}/db.dump"

# 5) Make the archived bootstrap files available to the operator (live files are
#    mounted read-only, so we cannot overwrite them in place).
restored="/backups/restored-bootstrap-$(date -u +%Y-%m-%dT%H-%M-%SZ)"
if [ -f "${workdir}/.env" ] || [ -f "${workdir}/config.yaml" ]; then
  mkdir -p "$restored"
  [ -f "${workdir}/.env" ] && cp "${workdir}/.env" "$restored/.env"
  [ -f "${workdir}/config.yaml" ] && cp "${workdir}/config.yaml" "$restored/config.yaml"
  echo "restore: archived bootstrap files placed in ${restored} (copy them next to the compose if needed)"
fi

echo "restore: done — start the app:  docker compose up -d"
