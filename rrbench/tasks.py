from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import os
from pathlib import Path

import yaml


class TeamModification(str, Enum):
    EVS = "evs"
    ABILITIES = "abilities"
    NATURES = "natures"
    MOVES = "moves"
    ITEMS = "items"
    POKEMON = "pokemon"


@dataclass(frozen=True)
class TaskSpec:
    """The runtime assets needed to start one task."""

    id: str
    rom_path: Path
    save_state_path: Path
    allowed_team_modifications: frozenset[TeamModification]
    level_cap: int
    team_size: int = 6
    allowed_species_ids: frozenset[int] | None = None


def load_task(task_dir: str | Path) -> TaskSpec:
    """Load a task manifest and resolve its emulator assets."""
    task_dir = Path(task_dir).resolve()
    manifest_path = task_dir / "task.yaml"
    manifest_text = manifest_path.read_text()
    manifest = yaml.safe_load(manifest_text)
    task_data_dir = Path(
        os.environ.get("RRBENCH_TASK_DATA_DIR", task_dir / "data" / "validation")
    )
    allowed_species_ids = None
    allowed_species_path = task_data_dir / "allowed_species_ids.json"
    if allowed_species_path.is_file():
        allowed_species_data = json.loads(allowed_species_path.read_text())
        species_ids = allowed_species_data.get("species_ids")
        if not isinstance(species_ids, list) or not all(
            type(species_id) is int for species_id in species_ids
        ):
            raise ValueError("allowed_species_ids.json must contain integer species_ids")
        task_yaml_sha256 = allowed_species_data.get("task_yaml_sha256")
        if task_yaml_sha256 is not None and task_yaml_sha256 != hashlib.sha256(
            manifest_text.encode()
        ).hexdigest():
            raise ValueError("allowed_species_ids.json does not match task.yaml")
        allowed_species_ids = frozenset(species_ids)
    return TaskSpec(
        id=manifest["id"],
        rom_path=Path(__file__).resolve().parents[1] / "radicalred.gba",
        save_state_path=task_dir / manifest["save_state"],
        allowed_team_modifications=frozenset(
            TeamModification(value)
            for value in manifest.get("allowed_team_modifications", [])
        ),
        level_cap=manifest["level_cap"],
        team_size=manifest.get("team_size", 6),
        allowed_species_ids=allowed_species_ids,
    )
