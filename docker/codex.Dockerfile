FROM node:22.17.0-bookworm-slim

ARG CODEX_VERSION=0.144.1

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates python3 \
    && rm -rf /var/lib/apt/lists/* \
    && npm install --global "@openai/codex@${CODEX_VERSION}" \
    && npm cache clean --force

COPY docker/agent-profile.sh /etc/profile.d/rrbench.sh

USER node
WORKDIR /workspace/scratch
