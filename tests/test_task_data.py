import hashlib
import json
from dataclasses import replace
from pathlib import Path

import yaml
import pytest

from rrbench.emulator.memory import PARTY_COUNT_ADDR
from rrbench.interface import service as service_module
from rrbench.interface.service import BattleService
from rrbench.tasks import BattleTriggerStep, TaskSpec, load_task
from tests.support.fakes import FakeEmulator


@pytest.mark.parametrize("team_size", [0, 7, True, "6"])
def test_load_task_rejects_invalid_team_size(tmp_path, team_size) -> None:
    task_directory = tmp_path / "task"
    task_directory.mkdir()
    (task_directory / "task.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "test",
                "save_state": "save_state.ss0",
                "level_cap": 57,
                "team_size": team_size,
            }
        )
    )

    with pytest.raises(ValueError, match="team_size must be an integer from 1 through 6"):
        load_task(task_directory)


def test_load_task_parses_battle_trigger(tmp_path) -> None:
    task_directory = tmp_path / "task"
    task_directory.mkdir()
    (task_directory / "task.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "test",
                "save_state": "save_state.ss0",
                "level_cap": 57,
                "battle_trigger": [
                    {"key": "UP", "frames": 60},
                    {"key": None, "frames": 20},
                ],
            }
        )
    )

    task = load_task(task_directory)

    assert task.battle_trigger == (
        BattleTriggerStep(key="UP", frames=60),
        BattleTriggerStep(key=None, frames=20),
    )


def test_load_task_parses_starter_line_species_ids(tmp_path) -> None:
    task_directory = tmp_path / "task"
    validation_directory = task_directory / "data" / "validation"
    validation_directory.mkdir(parents=True)
    manifest = {
        "id": "test",
        "save_state": "save_state.ss0",
        "level_cap": 15,
    }
    manifest_text = yaml.safe_dump(manifest)
    (task_directory / "task.yaml").write_text(manifest_text)
    (validation_directory / "allowed_species_ids.json").write_text(
        json.dumps(
            {
                "species_ids": [1, 4, 25],
                "task_yaml_sha256": hashlib.sha256(manifest_text.encode()).hexdigest(),
                "starter_line_species_ids": [1, 4],
            }
        )
    )

    task = load_task(task_directory)

    assert task.starter_line_species_ids == frozenset({1, 4})


def test_giovanni_agent_data_matches_the_validator_allowlist(monkeypatch) -> None:
    repository = Path(__file__).resolve().parents[1]
    task_directory = repository / "tasks" / "giovanni-silph-co-easy"
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
    assert species[478]["name"] == "Drifloon"
    assert species[479]["name"] == "Drifblim"
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


def test_rival_route_22_excludes_item_evolutions_without_celadon(monkeypatch) -> None:
    repository = Path(__file__).resolve().parents[1]
    task_directory = repository / "tasks" / "rival-route-22"
    monkeypatch.delenv("RRBENCH_TASK_DATA_DIR", raising=False)

    task = load_task(task_directory)
    species = json.loads((task_directory / "data" / "agent" / "species.json").read_text())

    assert task.allowed_species_ids is not None
    assert len(task.allowed_species_ids) == 54
    assert species[568]["name"] == "Panpour"
    assert species[569] is None
    assert species[1023]["name"] == "Sandshrew"
    assert species[1024] is None


def test_battle_service_ignores_unavailable_pre_evolution_learnsets(
    monkeypatch, party_memory
) -> None:
    repository = Path(__file__).resolve().parents[1]
    task_directory = repository / "tasks" / "giovanni-silph-co-easy"
    task = replace(load_task(task_directory), team_size=2)
    emulator = FakeEmulator(party_memory)
    monkeypatch.setattr(service_module, "create_emulator", lambda current_task: emulator)
    monkeypatch.setattr(service_module, "data_dir", task_directory / "data" / "agent")
    service = BattleService(task)
    members = [
        {
            "slot": slot,
            "species_id": 1,
            "level": 57,
            "nature_id": 0,
            "ability_id": 65,
            "move_ids": [33, 45, 73, 345],
            "held_item_id": 0,
            "evs": {"HP": 0, "ATK": 0, "DEF": 0, "SPE": 0, "SPA": 0, "SPDEF": 0},
        }
        for slot in range(2)
    ]
    members[0] = {
        "slot": 0,
        "species_id": 184,
        "level": 57,
        "nature_id": 3,
        "ability_id": 37,
        "move_ids": [358, 463, 357, 276],
        "held_item_id": 0,
        "evs": {"HP": 252, "ATK": 252, "DEF": 4, "SPE": 0, "SPA": 0, "SPDEF": 0},
    }

    result = service.apply_team({"members": members})

    assert result["ok"] is True
    assert service.active_team_config is not None
    assert service.active_team_config.members[0].species_id == 184


def test_initial_team_configuration_does_not_require_fixture_members(
    monkeypatch, party_memory
) -> None:
    repository = Path(__file__).resolve().parents[1]
    task_directory = repository / "tasks" / "giovanni-silph-co-easy"
    task = replace(load_task(task_directory), team_size=2)
    party_memory.load_u8(PARTY_COUNT_ADDR, 1)
    emulator = FakeEmulator(party_memory)
    monkeypatch.setattr(service_module, "create_emulator", lambda current_task: emulator)
    monkeypatch.setattr(service_module, "data_dir", task_directory / "data" / "agent")
    service = BattleService(task)
    members = [
        {
            "slot": slot,
            "species_id": 944,
            "level": 57,
            "nature_id": 8,
            "ability_id": 22,
            "move_ids": [434, 269, 585, 252],
            "held_item_id": 139,
            "evs": {"HP": 0, "ATK": 0, "DEF": 0, "SPE": 0, "SPA": 0, "SPDEF": 0},
        }
        for slot in range(2)
    ]

    result = service.apply_team({"members": members})

    assert result["ok"] is True
    assert service.active_team_config is not None
    assert len(service.active_team_config.members) == 2


def test_giovanni_agent_items_match_the_validator_allowlist(monkeypatch) -> None:
    repository = Path(__file__).resolve().parents[1]
    task_directory = repository / "tasks" / "giovanni-silph-co-easy"
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
    assert items_by_id[703] == {
        "id": 703,
        "name": "Air Balloon",
        "description": "An item to be held by a Pokémon. The holder floats in the air until hit. Once hit, this item will burst.",
        "count": 1,
    }
    assert 198 not in items_by_id
    assert 677 not in items_by_id


def test_giovanni_agent_tm_hm_moves_match_allowed_locations():
    repository = Path(__file__).resolve().parents[1]
    task_directory = repository / "tasks" / "giovanni-silph-co-easy"
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


def test_battle_service_rejects_duplicate_pokemon_identity(monkeypatch, party_memory) -> None:
    emulator = FakeEmulator(party_memory)
    task = TaskSpec(
        id="test",
        rom_path=Path("test.gba"),
        save_state_path=Path("test.ss0"),
        allowed_team_modifications=frozenset(),
        level_cap=15,
        team_size=2,
        allowed_species_ids=frozenset({1}),
    )
    monkeypatch.setattr(service_module, "create_emulator", lambda current_task: emulator)
    service = BattleService(task)

    result = service.apply_team(
        {
            "members": [
                {"slot": 0, "species_id": 1, "level": 15},
                {"slot": 1, "species_id": 1, "level": 15},
            ]
        }
    )

    assert result == {
        "ok": False,
        "error": "team members must have unique Pokemon identities",
    }


def test_battle_service_allows_at_most_one_starter(monkeypatch, party_memory) -> None:
    emulator = FakeEmulator(party_memory)
    task = TaskSpec(
        id="test",
        rom_path=Path("test.gba"),
        save_state_path=Path("test.ss0"),
        allowed_team_modifications=frozenset(),
        level_cap=15,
        team_size=2,
        allowed_species_ids=frozenset({1, 4}),
        starter_line_species_ids=frozenset({1, 4}),
    )
    monkeypatch.setattr(service_module, "create_emulator", lambda current_task: emulator)
    service = BattleService(task)

    result = service.apply_team(
        {
            "members": [
                {"slot": 0, "species_id": 1, "level": 15},
                {"slot": 1, "species_id": 4, "level": 15},
            ]
        }
    )

    assert result == {
        "ok": False,
        "error": "a team may contain at most one starter Pokemon",
    }
    assert service.active_team_config is None


def test_battle_service_allows_one_starter(monkeypatch, party_memory) -> None:
    emulator = FakeEmulator(party_memory)
    task = TaskSpec(
        id="test",
        rom_path=Path("test.gba"),
        save_state_path=Path("test.ss0"),
        allowed_team_modifications=frozenset(),
        level_cap=15,
        team_size=2,
        allowed_species_ids=frozenset({1, 25}),
        starter_line_species_ids=frozenset({1}),
    )
    monkeypatch.setattr(service_module, "create_emulator", lambda current_task: emulator)
    service = BattleService(task)

    result = service.apply_team(
        {
            "members": [
                {"slot": 0, "species_id": 1, "level": 15},
                {"slot": 1, "species_id": 25, "level": 15},
            ]
        }
    )

    assert result["ok"] is True


def test_battle_service_counts_starter_evolutions(monkeypatch, party_memory) -> None:
    emulator = FakeEmulator(party_memory)
    task = TaskSpec(
        id="test",
        rom_path=Path("test.gba"),
        save_state_path=Path("test.ss0"),
        allowed_team_modifications=frozenset(),
        level_cap=16,
        team_size=2,
        allowed_species_ids=frozenset({1, 2}),
        starter_line_species_ids=frozenset({1, 2}),
    )
    monkeypatch.setattr(service_module, "create_emulator", lambda current_task: emulator)
    service = BattleService(task)

    result = service.apply_team(
        {
            "members": [
                {"slot": 0, "species_id": 1, "level": 16},
                {"slot": 1, "species_id": 2, "level": 16},
            ]
        }
    )

    assert result == {
        "ok": False,
        "error": "a team may contain at most one starter Pokemon",
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
    member = {"slot": 0, "species_id": 150, "level": 100}

    result = service.apply_team({"members": [member, dict(member, slot=1)]})

    assert result == {"ok": False, "error": "species_id is not available for this task"}
