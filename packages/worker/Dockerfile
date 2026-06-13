# Container worker — phase 0 stub (0.T4): heartbeat loop only.
# Replaced by the real dispatcher + runner in 4.B1.
#
# Same multi-stage shape as packages/web (INF-5); the build stage will
# host poetry install once the real worker lands.
# Build context is the REPO ROOT: docker build -f packages/worker/Dockerfile .

FROM python:3.12-slim-bookworm AS build
WORKDIR /build
COPY packages/worker/stub/ ./stub/

FROM python:3.12-slim-bookworm
RUN useradd --system --no-create-home app
WORKDIR /app
COPY --from=build /build/stub/ ./stub/
USER app
CMD ["python", "/app/stub/worker.py"]
