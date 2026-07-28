import os
from pathlib import Path

from fastmcp import FastMCP

from rrbench.harness.trial import Trial
from rrbench.interface.service import BattleService
from rrbench.tasks import load_task

mcp = FastMCP("rrbench-battle")
task = load_task(os.environ["RRBENCH_TASK_DIR"])
service = BattleService(task)
trial = Trial(
    task=task,
    max_episodes=int(os.environ["RRBENCH_MAX_EPISODES"]),
    trajectory_path=Path(os.environ.get("RRBENCH_TRAJECTORY_PATH", "/var/log/battle/trajectory.jsonl")),
    score_path=Path(os.environ.get("RRBENCH_SCORE_PATH", "/var/log/battle/score.json")),
)


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
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)
