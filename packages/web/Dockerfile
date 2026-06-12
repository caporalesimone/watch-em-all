# Container web — phase 0 stub (0.T3): placeholder page + /api/health mock.
# Replaced by the real FastAPI app (1.B2) and the built SPA (1.F1).
#
# Multi-stage from day one (INF-5): today the build stage only stages the
# static placeholder; it will host the frontend build and poetry install.
# Build context is the REPO ROOT: docker build -f packages/web/Dockerfile .

FROM python:3.12-slim-bookworm AS build
WORKDIR /build
COPY packages/web/stub/ ./stub/

FROM python:3.12-slim-bookworm
RUN useradd --system --no-create-home app
WORKDIR /app
COPY --from=build /build/stub/ ./stub/
USER app
EXPOSE 8080
CMD ["python", "/app/stub/server.py"]
