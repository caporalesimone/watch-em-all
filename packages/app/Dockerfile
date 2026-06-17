# Container app — phase 0 stub + product-version baking (1.T4). ONE image, two
# roles (web | worker) selected by the command at runtime. web and worker share
# one codebase, one pyproject/lock and the same plugins (build-system.md) — they
# are one application with two roles, so they ship as a single image. Replaced by
# the real FastAPI app (1.B2) and worker (4.B1).
#
# Multi-stage from day one (INF-5): today the build stage stages the stub and
# derives the product version from the git history; it will host the frontend
# build and the poetry install. Build context is the REPO ROOT:
#   docker build -f packages/app/Dockerfile .

FROM python:3.12-slim-bookworm AS build
# git lives ONLY in this build stage: the product version's single source of
# truth is the git tag (ci.md). `git describe` reads .git refs only (no working
# tree), so the filtered build context is fine and `--dirty` is intentionally
# omitted. The final image carries just the computed string — never .git or git.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY .git/ ./.git/
# Bare x.y.z on a tag, x.y.z-N-g<sha> off a tag; "0.0.0-unknown" with no history.
RUN git config --global --add safe.directory /build \
    && { git -C /build describe --tags --always > VERSION 2>/dev/null \
         || echo "0.0.0-unknown" > VERSION; } \
    && printf 'baked product version: %s\n' "$(cat VERSION)"
COPY packages/app/stub/ ./stub/

FROM python:3.12-slim-bookworm
# curl is the healthcheck probe (compose: curl -fsS .../api/health). Kept minimal:
# no recommends, apt lists wiped in the same layer. The release compose uses the
# same command, so dev and release share one healthcheck (no python/curl split).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --system --no-create-home app
WORKDIR /app
COPY --from=build /build/VERSION /app/VERSION
COPY --from=build /build/stub/ ./stub/
COPY --chmod=0755 packages/app/entrypoint.sh /app/entrypoint.sh
USER app
EXPOSE 8080
ENTRYPOINT ["/app/entrypoint.sh"]
# Role passed as the command; the dev/release compose set `command: ["web"]` / ["worker"].
CMD ["web"]
