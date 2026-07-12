from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class TaskSpec:
    """The runtime assets needed to start one task."""

    id: str
    rom_path: Path
    save_state_path: Path
    # TODO: add more configurability: level cap, allowed team modifications, etc.


def load_task(task_dir: str | Path, *, rom_path: str | Path) -> TaskSpec:
    """Load a task manifest and resolve its emulator assets."""
    task_dir = Path(task_dir).resolve()
    manifest = yaml.safe_load((task_dir / "task.yaml").read_text())
    return TaskSpec(
        id=manifest["id"],
        rom_path=Path(rom_path).resolve(),
        save_state_path=task_dir / manifest["save_state"],
    )
