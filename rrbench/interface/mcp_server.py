import json
import os
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.tools.base import ToolResult
from mcp.types import TextContent

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


def text_result(result: dict) -> ToolResult:
    """Return one JSON text representation, without duplicate structured content."""
    return ToolResult(
        content=[
            TextContent(
                type="text",
                text=json.dumps(result, separators=(",", ":"), ensure_ascii=False),
            )
        ]
    )


@mcp.tool(output_schema=None)
def observe() -> ToolResult:
    return text_result(trial.handle({"verb": "observe"}, service))


@mcp.tool(output_schema=None)
def team() -> ToolResult:
    return text_result(trial.handle({"verb": "team"}, service))


@mcp.tool(output_schema=None)
def lead(pokemon: str) -> ToolResult:
    return text_result(trial.handle({"verb": "lead", "pokemon": pokemon}, service))


@mcp.tool(output_schema=None)
def action(command: str) -> ToolResult:
    return text_result(trial.handle({"verb": "action", "command": command}, service))


@mcp.tool(output_schema=None)
def apply_team(team: dict) -> ToolResult:
    return text_result(trial.handle({"verb": "apply-team", "team": team}, service))


@mcp.tool(output_schema=None)
def reset() -> ToolResult:
    return text_result(trial.handle({"verb": "reset"}, service))


if __name__ == "__main__":
    port = int(os.environ.get("RRBENCH_PORT", "8000"))
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
