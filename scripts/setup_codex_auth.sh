#!/bin/sh
# Authenticate Codex for rrbench evaluations.

set -eu

scriptDir="$(CDPATH= cd "$(dirname "$0")" && pwd)"
projectDir="$(dirname "$scriptDir")"

cd "$projectDir"

exec uv run rrbench-runner --agent codex --auth-setup \
    --credential-dir "$HOME/.local/share/rrbench/auth/codex" \
    --egress-network rrbench-egress \
    --egress-proxy http://provider-proxy:3128
