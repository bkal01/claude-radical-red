#!/usr/bin/env bash
set -euo pipefail

mkdir -p /logs/verifier

python3 - <<'PY'
import json
from pathlib import Path

trajectory_path = Path("/var/log/battle/trajectory.jsonl")
reward_path = Path("/logs/verifier/reward.txt")
reward = "0\n"

try:
    for line in reversed(trajectory_path.read_text().splitlines()):
        event = json.loads(line)
        if event.get("type") == "score":
            reward = "1\n" if event.get("status") == "won" else "0\n"
            break
except (OSError, json.JSONDecodeError):
    pass

reward_path.write_text(reward)
PY
