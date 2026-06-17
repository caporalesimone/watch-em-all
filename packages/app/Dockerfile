# Container app — web + worker roles (build-system.md). web runs the real FastAPI
# app (1.B2); worker is still a stub until phase 4 (4.B1). One image, role chosen
# by the entrypoint command. Multi-stage (INF-5): the build stage installs the
# Python deps and derives the product version; the final image carries no build
# tools, no git and no .git. Build context is the REPO ROOT:
#   docker build -f packages/app/Dockerfile .

FROM python:3.12-slim-bookworm AS build
ENV PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=2.3.3 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1
# git: needed only here to derive the product version (single source of truth =
# git tag, ci.md). git describe reads .git refs only; --dirty is omitted because
# the build context is a filtered copy of the tree.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
RUN pip install "poetry==${POETRY_VERSION}"
WORKDIR /build
# Dependency layer first (only the manifests) so a code change keeps the cache.
COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root
# Product version baked from git.
COPY .git/ ./.git/
RUN git config --global --add safe.directory /build \
    && { git -C /build describe --tags --always > VERSION 2>/dev/null \
         || echo "0.0.0-unknown" > VERSION; } \
    && printf 'baked product version: %s\n' "$(cat VERSION)"

FROM python:3.12-slim-bookworm
# curl is the healthcheck probe (compose: curl -fsS .../api/health). Kept minimal.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --system --no-create-home app
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app
COPY --from=build /build/.venv /app/.venv
COPY --from=build /build/VERSION /app/VERSION
COPY config.yaml /app/config.yaml
COPY src/ /app/src/
COPY packages/app/stub/worker.py /app/stub/worker.py
COPY --chmod=0755 packages/app/entrypoint.sh /app/entrypoint.sh
USER app
EXPOSE 8080
ENTRYPOINT ["/app/entrypoint.sh"]
# Role passed as the command; the dev/release compose set `command: ["web"]` / ["worker"].
CMD ["web"]
