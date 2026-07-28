FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install --yes --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
