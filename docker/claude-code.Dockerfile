FROM node:22.17.0-bookworm-slim

ARG CLAUDE_CODE_VERSION=2.1.202

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates python3 \
    && rm -rf /var/lib/apt/lists/* \
    && npm install --global "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" \
    && npm cache clean --force

COPY docker/agent-profile.sh /etc/profile.d/rrbench.sh

USER node
WORKDIR /workspace/scratch
