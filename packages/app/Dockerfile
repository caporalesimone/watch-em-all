# Container app — phase 0 stub. ONE image, two roles (web | worker) selected by the
# command at runtime. web and worker share one codebase, one pyproject/lock and the
# same plugins (build-system.md) — they are one application with two roles, so they
# ship as a single image. Replaced by the real FastAPI app (1.B2) and worker (4.B1).
#
# Multi-stage from day one (INF-5): today the build stage only stages the stub; it
# will host the frontend build and the poetry install.
# Build context is the REPO ROOT: docker build -f packages/app/Dockerfile .

FROM python:3.12-slim-bookworm AS build
WORKDIR /build
COPY packages/app/stub/ ./stub/

FROM python:3.12-slim-bookworm
RUN useradd --system --no-create-home app
WORKDIR /app
COPY --from=build /build/stub/ ./stub/
COPY --chmod=0755 packages/app/entrypoint.sh /app/entrypoint.sh
USER app
EXPOSE 8080
ENTRYPOINT ["/app/entrypoint.sh"]
# Role passed as the command; the dev/release compose set `command: ["web"]` / ["worker"].
CMD ["web"]
