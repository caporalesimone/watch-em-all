# Container app — web + worker roles (build-system.md). web runs the real FastAPI
# app (1.B2) and serves the built SPA (1.F*); worker is still a stub until phase 4
# (4.B1). One image, role chosen by the entrypoint command. Multi-stage (INF-5):
# a node stage builds the SPA, a python stage installs deps and derives the
# version; the final image has no build tools, no node, no git, no .git.
# Build context is the REPO ROOT: docker build -f packages/app/Dockerfile .

FROM node:22-slim AS frontend
# Build the SvelteKit SPA (adapter-static → build/); baked into the image and
# served by FastAPI (spa.py). The repo layout is preserved (/src/frontend with a
# /src/plugins sibling) so the `$plugins` alias and the build:plugins generator
# resolve the plugin frontends exactly as they do in the repo. Dependency layer
# first so source edits keep the cache.
WORKDIR /src/frontend
COPY src/frontend/package.json src/frontend/package-lock.json ./
RUN npm ci
COPY src/frontend/ ./
# Plugin frontends live in a sibling folder and are bundled by the single build.
COPY src/plugins/ /src/plugins/
RUN npm run build

FROM python:3.12-slim-bookworm AS build
ENV PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=2.3.3 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1
# git: derive the product version (single source of truth = git tag, ci.md).
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
    PYTHONPATH=/app \
    WEA_STATIC_DIR=/app/static
COPY --from=build /build/.venv /app/.venv
COPY --from=build /build/VERSION /app/VERSION
COPY --from=frontend /src/frontend/build /app/static
COPY config.yaml /app/config.yaml
COPY src/__init__.py /app/src/__init__.py
COPY src/core /app/src/core
COPY src/web /app/src/web
# Plugins are auto-discovered at startup (registry) and their icons are served as
# static assets, so the whole folder (manifest + backend + icon) ships in the image.
COPY src/plugins /app/src/plugins
COPY packages/app/stub/worker.py /app/stub/worker.py
COPY --chmod=0755 packages/app/entrypoint.sh /app/entrypoint.sh
USER app
EXPOSE 8080
ENTRYPOINT ["/app/entrypoint.sh"]
# Role passed as the command; the dev/release compose set `command: ["web"]` / ["worker"].
CMD ["web"]
