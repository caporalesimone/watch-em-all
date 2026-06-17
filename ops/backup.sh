#!/usr/bin/env bash
# Full backup (1.T2, INF-16): pg_dump (custom format) + the bootstrap files
# (.env, and config.yaml if a local override is mounted) into a single dated
# tarball under /backups. Runs hot — pg_dump uses a consistent MVCC snapshot.
set -euo pipefail

export PGHOST="${PGHOST:-db}"
export PGUSER="${PGUSER:-${POSTGRES_USER:-watchemall}}"
export PGPASSWORD="${PGPASSWORD:-${POSTGRES_PASSWORD:-}}"
export PGDATABASE="${PGDATABASE:-${POSTGRES_DB:-watchemall}}"

stamp="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

echo "backup: dumping database '${PGDATABASE}' from '${PGHOST}'…"
pg_dump --format=custom --file="${workdir}/db.dump"

# Bootstrap files are mounted read-only under /host (deployment.md). .env carries
# secrets, so the archive does too — store it accordingly. Absence is fine.
[ -f /host/.env ] && cp /host/.env "${workdir}/.env" || echo "backup: no /host/.env mounted, skipping"
[ -f /host/config.yaml ] && cp /host/config.yaml "${workdir}/config.yaml" || true

archive="/backups/watchemall-backup-${stamp}.tar.gz"
tar -czf "$archive" -C "$workdir" .
echo "backup: wrote ${archive}"
