# Container ops — phase 0 stub (0.T4): postgres:16 client tools + the
# (placeholder) backup/export/restore scripts from ops/ (INF-16).
# Real scripts arrive with 1.T2/1.T3 and land here unchanged: the image
# just bakes whatever ops/ contains.
# Build context is the REPO ROOT: docker build -f packages/ops/Dockerfile .
#
# Ephemeral by design: one script per run, never a long-running service
# (docker compose run --rm ops backup.sh — deployment.md).

FROM postgres:16
COPY --chmod=0755 ops/*.sh /usr/local/bin/
CMD ["bash", "-c", "echo 'usage: docker compose run --rm ops {backup.sh|export.sh|restore.sh}' >&2; exit 64"]
