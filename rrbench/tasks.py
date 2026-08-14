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
class BattleTriggerStep:
    key: str | None
    frames: int


@dataclass(frozen=True)
class TaskSpec:
    """The runtime assets needed to start one task."""

    id: str
    rom_path: Path
    save_state_path: Path
    allowed_team_modifications: frozenset[TeamModification]
    level_cap: int
    team_size: int = 6
    battle_trigger: tuple[BattleTriggerStep, ...] = ()
    allowed_species_ids: frozenset[int] | None = None
    allowed_item_ids: frozenset[int] | None = None
    allowed_item_counts: dict[int, int] | None = None


def load_task(task_dir: str | Path) -> TaskSpec:
    """Load a task manifest and resolve its emulator assets."""
    task_dir = Path(task_dir).resolve()
    manifest_path = task_dir / "task.yaml"
    manifest_text = manifest_path.read_text()
    manifest = yaml.safe_load(manifest_text)
    team_size = manifest.get("team_size", 6)
    if type(team_size) is not int or team_size not in range(1, 7):
        raise ValueError("team_size must be an integer from 1 through 6")
    battle_trigger_value = manifest.get("battle_trigger", [])
    if not isinstance(battle_trigger_value, list):
        raise ValueError("battle_trigger must be a list")
    battle_trigger = []
    trigger_keys = {"A", "B", "UP", "DOWN", "LEFT", "RIGHT"}
    for trigger_index, trigger_value in enumerate(battle_trigger_value):
        if not isinstance(trigger_value, dict) or set(trigger_value) != {"key", "frames"}:
            raise ValueError(
                f"battle_trigger[{trigger_index}] must contain only key and frames"
            )
        key = trigger_value["key"]
        frames = trigger_value["frames"]
        if key is not None and (not isinstance(key, str) or key not in trigger_keys):
            raise ValueError(
                f"battle_trigger[{trigger_index}].key must be one of "
                f"{', '.join(sorted(trigger_keys))}, or null"
            )
        if type(frames) is not int or frames < 1:
            raise ValueError(
                f"battle_trigger[{trigger_index}].frames must be a positive integer"
            )
        battle_trigger.append(BattleTriggerStep(key=key, frames=frames))
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
    allowed_item_ids = None
    allowed_item_counts = None
    allowed_items_path = task_data_dir / "allowed_item_ids.json"
    if allowed_items_path.is_file():
        allowed_items_data = json.loads(allowed_items_path.read_text())
        item_ids = allowed_items_data.get("item_ids")
        if not isinstance(item_ids, list) or not all(
            type(item_id) is int for item_id in item_ids
        ):
            raise ValueError("allowed_item_ids.json must contain integer item_ids")
        task_yaml_sha256 = allowed_items_data.get("task_yaml_sha256")
        if task_yaml_sha256 is not None and task_yaml_sha256 != hashlib.sha256(
            manifest_text.encode()
        ).hexdigest():
            raise ValueError("allowed_item_ids.json does not match task.yaml")
        allowed_item_ids = frozenset(item_ids)
        item_counts = allowed_items_data.get("item_counts")
        if item_counts is not None:
            expected_item_count_ids = {str(item_id) for item_id in item_ids}
            if (
                not isinstance(item_counts, dict)
                or set(item_counts) != expected_item_count_ids
                or any(type(count) is not int or count < 1 for count in item_counts.values())
            ):
                raise ValueError(
                    "allowed_item_ids.json must contain positive integer item_counts for every item_id"
                )
            allowed_item_counts = {
                int(item_id): count for item_id, count in item_counts.items()
            }
    return TaskSpec(
        id=manifest["id"],
        rom_path=Path(__file__).resolve().parents[1] / "radicalred.gba",
        save_state_path=task_dir / manifest["save_state"],
        allowed_team_modifications=frozenset(
            TeamModification(value)
            for value in manifest.get("allowed_team_modifications", [])
        ),
        level_cap=manifest["level_cap"],
        team_size=team_size,
        battle_trigger=tuple(battle_trigger),
        allowed_species_ids=allowed_species_ids,
        allowed_item_ids=allowed_item_ids,
        allowed_item_counts=allowed_item_counts,
    )
