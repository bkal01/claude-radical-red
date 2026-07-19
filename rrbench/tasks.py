from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import yaml


class TeamModification(str, Enum):
    EVS = "evs"


@dataclass(frozen=True)
class TaskSpec:
    """The runtime assets needed to start one task."""

    id: str
    rom_path: Path
    save_state_path: Path
    allowed_team_modifications: frozenset[TeamModification]


def load_task(task_dir: str | Path) -> TaskSpec:
    """Load a task manifest and resolve its emulator assets."""
    task_dir = Path(task_dir).resolve()
    manifest = yaml.safe_load((task_dir / "task.yaml").read_text())
    return TaskSpec(
        id=manifest["id"],
        rom_path=Path(__file__).resolve().parents[1] / "radicalred.gba",
        save_state_path=task_dir / manifest["save_state"],
        allowed_team_modifications=frozenset(
            TeamModification(value)
            for value in manifest.get("allowed_team_modifications", [])
        ),
    )
