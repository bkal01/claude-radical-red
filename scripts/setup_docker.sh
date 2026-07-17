#!/bin/sh
# Build the evaluation images and configure the provider proxy network.

set -eu

scriptDir="$(CDPATH= cd "$(dirname "$0")" && pwd)"
projectDir="$(dirname "$scriptDir")"
networkName="rrbench-egress"
proxyName="rrbench-provider-proxy"

if ! docker info >/dev/null 2>&1; then
    echo "Docker is not running. Start Docker and try again." >&2
    exit 1
fi

cd "$projectDir"

echo "Building rrbench server image..."
docker build -t rrbench-server:dev -f docker/rrbench-server.Dockerfile .

echo "Building provider proxy image..."
docker build -t rrbench-provider-proxy:dev -f docker/provider-proxy.Dockerfile .

if ! docker network inspect "$networkName" >/dev/null 2>&1; then
    echo "Creating internal egress network..."
    docker network create --internal "$networkName"
elif [ "$(docker network inspect "$networkName" --format '{{.Internal}}')" != "true" ]; then
    echo "Docker network $networkName exists but is not internal." >&2
    echo "Remove or rename it before rerunning this script." >&2
    exit 1
fi

if docker container inspect "$proxyName" >/dev/null 2>&1; then
    echo "Replacing existing provider proxy container..."
    docker rm -f "$proxyName" >/dev/null
fi

echo "Starting provider proxy..."
docker run -d \
    --name "$proxyName" \
    --network "$networkName" \
    --network-alias provider-proxy \
    rrbench-provider-proxy:dev >/dev/null

echo "Connecting provider proxy to Docker bridge network..."
docker network connect bridge "$proxyName"

echo "Docker evaluation setup is ready."
