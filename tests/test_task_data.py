import json
from pathlib import Path

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
