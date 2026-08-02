import os
from pathlib import Path

from fastmcp import FastMCP

from rrbench.harness.trial import Trial
from rrbench.interface.service import BattleService
from rrbench.tasks import load_task

mcp = FastMCP("rrbench-battle")
task = load_task(os.environ["RRBENCH_TASK_DIR"])
service = BattleService(task)
record_value = os.environ.get("RRBENCH_RECORD", "false")
record_enabled = record_value.lower() in {"1", "true", "yes", "on"}
trial = Trial(
    task=task,
    max_episodes=int(os.environ["RRBENCH_MAX_EPISODES"]),
    record=record_enabled,
    trajectory_path=Path(os.environ.get("RRBENCH_TRAJECTORY_PATH", "/var/log/battle/trajectory.jsonl")),
    score_path=Path(os.environ.get("RRBENCH_SCORE_PATH", "/var/log/battle/score.json")),
    videos_path=Path(os.environ.get("RRBENCH_VIDEO_DIR", "/var/log/battle/videos")),
)
trial.start(service)


@mcp.tool()
def observe() -> dict:
    return trial.handle({"verb": "observe"}, service)


@mcp.tool()
def team() -> dict:
    return trial.handle({"verb": "team"}, service)


@mcp.tool()
def lead(pokemon: str) -> dict:
    return trial.handle({"verb": "lead", "pokemon": pokemon}, service)


@mcp.tool()
def action(command: str) -> dict:
    return trial.handle({"verb": "action", "command": command}, service)


@mcp.tool()
def apply_team(team: dict) -> dict:
    return trial.handle({"verb": "apply-team", "team": team}, service)


@mcp.tool()
def reset() -> dict:
    return trial.handle({"verb": "reset"}, service)


if __name__ == "__main__":
    port = int(os.environ.get("RRBENCH_PORT", "8000"))
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
