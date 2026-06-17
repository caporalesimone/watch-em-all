#!/usr/bin/env bash
# Portable export (1.T2, INF-16): a readable plain-SQL dump, gzipped, for
# inspection, diff or migration to another installation. No bootstrap files,
# no secrets — just the schema and data. Runs hot (MVCC snapshot).
set -euo pipefail

export PGHOST="${PGHOST:-db}"
export PGUSER="${PGUSER:-${POSTGRES_USER:-watchemall}}"
export PGPASSWORD="${PGPASSWORD:-${POSTGRES_PASSWORD:-}}"
export PGDATABASE="${PGDATABASE:-${POSTGRES_DB:-watchemall}}"

stamp="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
archive="/backups/watchemall-export-${stamp}.sql.gz"

echo "export: dumping '${PGDATABASE}' as plain SQL…"
pg_dump --format=plain | gzip -c > "$archive"
echo "export: wrote ${archive}"
