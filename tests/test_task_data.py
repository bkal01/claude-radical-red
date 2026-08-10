import json
from pathlib import Path

import yaml

from rrbench.interface import service as service_module
from rrbench.interface.service import BattleService
from rrbench.tasks import TaskSpec, load_task
from tests.support.fakes import FakeEmulator


def test_giovanni_agent_data_matches_the_validator_allowlist(monkeypatch) -> None:
    repository = Path(__file__).resolve().parents[1]
    task_directory = repository / "tasks" / "giovanni"
    monkeypatch.delenv("RRBENCH_TASK_DATA_DIR", raising=False)

    task = load_task(task_directory)
    species = json.loads((task_directory / "data" / "agent" / "species.json").read_text())
    learnsets = json.loads((task_directory / "data" / "agent" / "learnsets.json").read_text())

    assert task.allowed_species_ids is not None
    assert {species_id for species_id, entry in enumerate(species) if entry} == task.allowed_species_ids
    assert {species_id for species_id, entry in enumerate(learnsets) if entry} == task.allowed_species_ids
    assert species[92]["name"] == "Gastly"
    assert species[93]["name"] == "Haunter"
    assert species[94]["name"] == "Gengar"
    assert species[29]["name"] == "Nidoran♀"
    assert species[32]["name"] == "Nidoran♂"
    assert species[680]["name"] == "Rufflet"
    assert species[681]["name"] == "Braviary"
    rotom_species_ids = {532, 713, 714, 715, 716, 717}
    assert rotom_species_ids <= task.allowed_species_ids
    assert all(species[species_id]["name"] == "Rotom" for species_id in rotom_species_ids)
    assert {1085, 1086, 1088, 1089, 1090, 1091, 1092} <= task.allowed_species_ids
    assert {1, 7, 138, 140, 147, 152, 246, 277, 395, 398} <= task.allowed_species_ids
    assert species[150] is None
    mega_species_ids = json.loads(
        (repository / "data" / "radical_red" / "v4.1" / "species_categories.json").read_text()
    )["mega"]
    assert all(species[species_id] is None for species_id in mega_species_ids)


def test_giovanni_agent_items_match_the_validator_allowlist(monkeypatch) -> None:
    repository = Path(__file__).resolve().parents[1]
    task_directory = repository / "tasks" / "giovanni"
    monkeypatch.delenv("RRBENCH_TASK_DATA_DIR", raising=False)

    task = load_task(task_directory)
    items = json.loads((task_directory / "data" / "agent" / "items.json").read_text())

    assert task.allowed_item_ids is not None
    assert task.allowed_item_counts is not None
    items_by_id = {item["id"]: item for item in items}
    assert set(items_by_id) == task.allowed_item_ids
    assert len(items_by_id) == len(items) == len(task.allowed_item_ids)
    assert all(set(item) == {"id", "name", "description", "count"} for item in items)
    assert {item_id: item["count"] for item_id, item in items_by_id.items()} == task.allowed_item_counts
    assert items_by_id[675]["name"] == "Wise Glasses"
    assert items_by_id[139]["count"] == 3
    assert items_by_id[142]["count"] == 1
    assert 198 not in items_by_id
    assert 677 not in items_by_id


def test_giovanni_agent_tm_hm_moves_match_allowed_locations():
    repository = Path(__file__).resolve().parents[1]
    task_directory = repository / "tasks" / "giovanni"
    data_directory = repository / "data" / "radical_red" / "v4.1"
    route_move_map = json.loads((data_directory / "route_move_map.json").read_text())
    moves = json.loads((data_directory / "moves.json").read_text())
    learnsets = json.loads((task_directory / "data" / "agent" / "learnsets.json").read_text())
    manifest = yaml.safe_load((task_directory / "task.yaml").read_text())
    move_name_aliases = {
        "Draining Kiss": "Drain Kiss",
        "Supercell Slam": "Soupercell Slam",
        "U-Turn": "U-turn",
    }
    move_ids_by_name = {
        move["name"]: move_id for move_id, move in enumerate(moves) if move
    }
    available_tm_hm_move_ids = {
        move_ids_by_name[move_name_aliases.get(move_name, move_name)]
        for location in manifest["allowed_locations"]
        for move_type in ("tms", "hms")
        for move_name in route_move_map.get(location, {}).get(move_type, [])
    }
    available_tutor_move_ids = {
        move_ids_by_name[move_name_aliases.get(move_name, move_name)]
        for location in manifest["allowed_locations"]
        for move_name in route_move_map.get(location, {}).get("tutors", [])
    }

    assert all(
        set(learnset["tm_hm"]) <= available_tm_hm_move_ids
        for learnset in learnsets
        if learnset
    )
    assert all(
        set(learnset["tutor"]) <= available_tutor_move_ids
        for learnset in learnsets
        if learnset
    )
    assert all(not learnset["egg"] for learnset in learnsets if learnset)
    assert len(available_tutor_move_ids) == 12
    assert move_ids_by_name["U-turn"] in {
        move_id for learnset in learnsets if learnset for move_id in learnset["tm_hm"]
    }
    assert move_ids_by_name["Soupercell Slam"] not in {
        move_id for learnset in learnsets if learnset for move_id in learnset["tm_hm"]
    }


def test_battle_service_rejects_species_outside_the_task_allowlist(
    monkeypatch, party_memory
) -> None:
    emulator = FakeEmulator(party_memory)
    task = TaskSpec(
        id="test",
        rom_path=Path("test.gba"),
        save_state_path=Path("test.ss0"),
        allowed_team_modifications=frozenset(),
        level_cap=100,
        team_size=2,
        allowed_species_ids=frozenset({1}),
    )
    monkeypatch.setattr(service_module, "create_emulator", lambda current_task: emulator)
    service = BattleService(task)
    member = {
        "slot": 0,
        "species_id": 150,
        "level": 100,
        "nature_id": 0,
        "ability_id": 0,
        "move_ids": [0, 0, 0, 0],
        "held_item_id": 0,
        "evs": {"HP": 0, "ATK": 0, "DEF": 0, "SPE": 0, "SPA": 0, "SPDEF": 0},
    }

    result = service.apply_team({"members": [member, dict(member, slot=1)]})

    assert result == {"ok": False, "error": "species_id is not available for this task"}
