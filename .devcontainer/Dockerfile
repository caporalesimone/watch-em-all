# Dev container toolchain. Versions mirror the build stages of the
# package images (same majors): Python 3.12 + Poetry, Node 22 LTS + npm —
# plus git and docker CLI. No gh: git/GitHub operations (commit, push,
# PR) happen from the HOST, the dev container only builds and runs.
FROM python:3.12-slim-bookworm

ARG NODE_MAJOR=22

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl git gnupg openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Node 22 LTS (NodeSource)
RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_MAJOR}.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Docker CLI + Compose plugin (docker-outside-of-docker: the engine is the host's)
RUN install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian bookworm stable" \
        > /etc/apt/sources.list.d/docker.list \
    && apt-get update && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*

# Poetry, with in-project venvs so the container stays disposable
RUN pip install --no-cache-dir "poetry>=2,<3" \
    && poetry config virtualenvs.in-project true
