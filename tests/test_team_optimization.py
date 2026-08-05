from pathlib import Path

import pytest

from rrbench.battle.addresses import BATTLE_TYPE_FLAGS
from rrbench.battle.state import BattleSession
from rrbench.emulator.memory import PARTY_BASE_ADDR, Party
from rrbench.harness.trial import Trial
from rrbench.interface import service as service_module
from rrbench.interface.service import BattleService
from rrbench.tasks import TaskSpec, TeamModification, load_task
from tests.support.fakes import FakeEmulator


def test_trial_applies_valid_ev_spreads(monkeypatch, party_memory, tmp_path) -> None:
    emulator = FakeEmulator(party_memory)
    task = TaskSpec(
        id="test",
        rom_path=Path("test.gba"),
        save_state_path=Path("test.ss0"),
        allowed_team_modifications=frozenset({TeamModification.EVS}),
        level_cap=100,
    )
    monkeypatch.setattr(service_module, "create_emulator", lambda task: emulator)

    party_memory.load_u32(BATTLE_TYPE_FLAGS, 1)
    service = BattleService(task)
    service.session = BattleSession(emu=emulator, party=Party(emulator.mem))
    original_team = service.original_team_config
    trial = Trial(
        task=task,
        max_episodes=2,
        trajectory_path=tmp_path / "trajectory.jsonl",
        score_path=tmp_path / "score.json",
    )

    team_payload = {
        "members": [
            {
                "slot": 0,
                "species_id": 1,
                "evs": {"HP": 252, "ATK": 0, "DEF": 4, "SPE": 0, "SPA": 0, "SPDEF": 252},
            },
            {
                "slot": 1,
                "species_id": 944,
                "evs": {"HP": 252, "ATK": 252, "DEF": 4, "SPE": 0, "SPA": 0, "SPDEF": 0},
            },
        ]
    }

    result = trial.handle({"verb": "apply-team", "team": team_payload}, service)

    assert result["ok"] is True
    assert trial.episodes == 2

    active_team = service.active_team_config
    assert active_team is not None
    assert result["observation"] == {
        "phase": "no_battle",
        "party": [
            {
                "name": "Bulbasaur",
                "current_hp": 136,
                "max_hp": 136,
                "status": "poison",
                "active": False,
                "fainted": False,
                "moves": [
                    {"name": "Pound", "pp_remaining": 10},
                    {"name": "Growl", "pp_remaining": 12},
                ],
            },
            {
                "name": "Incineroar",
                "current_hp": 186,
                "max_hp": 186,
                "status": None,
                "active": False,
                "fainted": False,
                "moves": [
                    {"name": "Ember", "pp_remaining": 20},
                    {"name": "Growl", "pp_remaining": 15},
                ],
            },
        ],
    }
    expected_stats = (
        {"HP": 136, "ATK": 54, "DEF": 54, "SPE": 50, "SPA": 70, "SPDEF": 101},
        {"HP": 186, "ATK": 166, "DEF": 85, "SPE": 65, "SPA": 85, "SPDEF": 95},
    )
    for slot, (original_member, active_member) in enumerate(
        zip(original_team.members, active_team.members)
    ):
        assert result["team"]["members"][slot]["stats"] == expected_stats[slot]
        assert active_member.species_id == original_member.species_id
        assert active_member.move_ids == original_member.move_ids
        assert active_member.ability_id == original_member.ability_id
        assert active_member.held_item == original_member.held_item

    assert result["team"]["members"][0]["evs"] == team_payload["members"][0]["evs"]
    assert result["team"]["members"][1]["evs"] == team_payload["members"][1]["evs"]


def test_trial_applies_valid_abilities_without_changing_natures(
    monkeypatch,
    party_memory,
    tmp_path,
) -> None:
    emulator = FakeEmulator(party_memory)
    task = TaskSpec(
        id="test",
        rom_path=Path("test.gba"),
        save_state_path=Path("test.ss0"),
        allowed_team_modifications=frozenset({TeamModification.ABILITIES}),
        level_cap=100,
    )
    monkeypatch.setattr(service_module, "create_emulator", lambda task: emulator)

    party_memory.load_u32(BATTLE_TYPE_FLAGS, 1)
    service = BattleService(task)
    service.session = BattleSession(emu=emulator, party=Party(emulator.mem))
    trial = Trial(
        task=task,
        max_episodes=2,
        trajectory_path=tmp_path / "trajectory.jsonl",
        score_path=tmp_path / "score.json",
    )

    result = trial.handle(
        {
            "verb": "apply-team",
            "team": {
                "members": [
                    {"slot": 0, "species_id": 1, "ability_id": 34},
                    {"slot": 1, "species_id": 944, "ability_id": 66},
                ]
            },
        },
        service,
    )

    assert result["ok"] is True
    assert trial.episodes == 2
    assert result["team"]["members"][0]["ability_id"] == 34
    assert result["team"]["members"][0]["ability"] == "Chlorophyll"
    assert result["team"]["members"][1]["ability_id"] == 66
    assert result["team"]["members"][1]["ability"] == "Blaze"

    assert result["observation"] == {
        "phase": "no_battle",
        "party": [
            {
                "name": "Bulbasaur",
                "current_hp": 105,
                "max_hp": 105,
                "status": "poison",
                "active": False,
                "fainted": False,
                "moves": [
                    {"name": "Pound", "pp_remaining": 10},
                    {"name": "Growl", "pp_remaining": 12},
                ],
            },
            {
                "name": "Incineroar",
                "current_hp": 155,
                "max_hp": 155,
                "status": None,
                "active": False,
                "fainted": False,
                "moves": [
                    {"name": "Ember", "pp_remaining": 20},
                    {"name": "Growl", "pp_remaining": 15},
                ],
            },
        ],
    }


def test_trial_applies_valid_moves_available_at_level_cap(
    monkeypatch,
    party_memory,
    tmp_path,
) -> None:
    emulator = FakeEmulator(party_memory)
    task = TaskSpec(
        id="test",
        rom_path=Path("test.gba"),
        save_state_path=Path("test.ss0"),
        allowed_team_modifications=frozenset({TeamModification.MOVES}),
        level_cap=57,
    )
    monkeypatch.setattr(service_module, "create_emulator", lambda task: emulator)

    party_memory.load_u32(BATTLE_TYPE_FLAGS, 1)
    service = BattleService(task)
    service.session = BattleSession(emu=emulator, party=Party(emulator.mem))
    original_team = service.original_team_config
    trial = Trial(
        task=task,
        max_episodes=2,
        trajectory_path=tmp_path / "trajectory.jsonl",
        score_path=tmp_path / "score.json",
    )
    team_payload = {
        "members": [
            {"slot": 0, "species_id": 1, "move_ids": [33, 45, 73, 345]},
            {"slot": 1, "species_id": 944, "move_ids": [365, 53, 126, 434]},
        ]
    }

    result = trial.handle({"verb": "apply-team", "team": team_payload}, service)

    assert result["ok"] is True
    assert trial.episodes == 2
    active_team = service.active_team_config
    assert active_team is not None
    assert active_team.members[0].move_ids == (33, 45, 73, 345)
    assert active_team.members[1].move_ids == (365, 53, 126, 434)
    assert Party(emulator.mem).members[0].move_ids == (33, 45, 73, 345)
    assert Party(emulator.mem).members[1].move_ids == (365, 53, 126, 434)
    for original_member, active_member in zip(original_team.members, active_team.members):
        assert active_member.species_id == original_member.species_id
        assert active_member.evs == original_member.evs
        assert active_member.ability_id == original_member.ability_id
        assert active_member.held_item == original_member.held_item

    assert result["team"]["members"][0]["moves"] == [
        {"slot": 0, "move_id": 33, "name": "Tackle"},
        {"slot": 1, "move_id": 45, "name": "Growl"},
        {"slot": 2, "move_id": 73, "name": "Leech Seed"},
        {"slot": 3, "move_id": 345, "name": "Magical Leaf"},
    ]
    assert result["team"]["members"][1]["moves"] == [
        {"slot": 0, "move_id": 365, "name": "Close Combat"},
        {"slot": 1, "move_id": 53, "name": "Flamethrower"},
        {"slot": 2, "move_id": 126, "name": "Fire Blast"},
        {"slot": 3, "move_id": 434, "name": "Flare Blitz"},
    ]


def test_trial_applies_valid_held_items(monkeypatch, party_memory, tmp_path) -> None:
    emulator = FakeEmulator(party_memory)
    task = TaskSpec(
        id="test",
        rom_path=Path("test.gba"),
        save_state_path=Path("test.ss0"),
        allowed_team_modifications=frozenset({TeamModification.ITEMS}),
        level_cap=100,
    )
    monkeypatch.setattr(service_module, "create_emulator", lambda task: emulator)

    party_memory.load_u32(BATTLE_TYPE_FLAGS, 1)
    service = BattleService(task)
    service.session = BattleSession(emu=emulator, party=Party(emulator.mem))
    original_team = service.original_team_config
    trial = Trial(
        task=task,
        max_episodes=2,
        trajectory_path=tmp_path / "trajectory.jsonl",
        score_path=tmp_path / "score.json",
    )
    team_payload = {
        "members": [
            {"slot": 0, "species_id": 1, "held_item_id": 0},
            {"slot": 1, "species_id": 944, "held_item_id": 711},
        ]
    }

    result = trial.handle({"verb": "apply-team", "team": team_payload}, service)

    assert result["ok"] is True
    assert trial.episodes == 2
    active_team = service.active_team_config
    assert active_team is not None
    assert [member.held_item for member in active_team.members] == [0, 711]
    assert [member.held_item for member in Party(emulator.mem).members] == [0, 711]
    assert [member["held_item_id"] for member in result["team"]["members"]] == [0, 711]
    for original_member, active_member in zip(original_team.members, active_team.members):
        assert active_member.species_id == original_member.species_id
        assert active_member.evs == original_member.evs
        assert active_member.ability_id == original_member.ability_id
        assert active_member.move_ids == original_member.move_ids


def test_trial_applies_pre_evolution_move_at_level_cap(
    monkeypatch,
    party_memory,
    tmp_path,
) -> None:
    emulator = FakeEmulator(party_memory)
    task = TaskSpec(
        id="test",
        rom_path=Path("test.gba"),
        save_state_path=Path("test.ss0"),
        allowed_team_modifications=frozenset(
            {
                TeamModification.POKEMON,
                TeamModification.EVS,
                TeamModification.ABILITIES,
                TeamModification.MOVES,
                TeamModification.ITEMS,
            }
        ),
        level_cap=57,
    )
    monkeypatch.setattr(service_module, "create_emulator", lambda task: emulator)

    party_memory.load_u32(BATTLE_TYPE_FLAGS, 1)
    service = BattleService(task)
    service.session = BattleSession(emu=emulator, party=Party(emulator.mem))
    trial = Trial(
        task=task,
        max_episodes=2,
        trajectory_path=tmp_path / "trajectory.jsonl",
        score_path=tmp_path / "score.json",
    )

    result = trial.handle(
        {
            "verb": "apply-team",
            "team": {
                "members": [
                    {
                        "slot": 0,
                        "species_id": 307,
                        "evs": {"HP": 0, "ATK": 0, "DEF": 0, "SPE": 0, "SPA": 0, "SPDEF": 0},
                        "ability_id": 27,
                        "move_ids": [147, 71, 33, 78],
                        "held_item_id": 0,
                    },
                    {
                        "slot": 1,
                        "species_id": 944,
                        "evs": {"HP": 0, "ATK": 0, "DEF": 0, "SPE": 0, "SPA": 0, "SPDEF": 0},
                        "ability_id": 66,
                        "move_ids": [365, 53, 126, 434],
                        "held_item_id": 0,
                    },
                ]
            },
        },
        service,
    )

    assert result["ok"] is True
    assert trial.episodes == 2
    assert result["team"]["members"][0]["name"] == "Breloom"
    assert result["team"]["members"][0]["moves"] == [
        {"slot": 0, "move_id": 147, "name": "Spore"},
        {"slot": 1, "move_id": 71, "name": "Absorb"},
        {"slot": 2, "move_id": 33, "name": "Tackle"},
        {"slot": 3, "move_id": 78, "name": "Stun Spore"},
    ]
    assert Party(emulator.mem).members[0].species_id == 307
    assert Party(emulator.mem).members[0].move_ids == (147, 71, 33, 78)


def test_trial_applies_valid_pokemon_replacement(monkeypatch, party_memory, tmp_path) -> None:
    emulator = FakeEmulator(party_memory)
    task = TaskSpec(
        id="test",
        rom_path=Path("test.gba"),
        save_state_path=Path("test.ss0"),
        allowed_team_modifications=frozenset(
            {
                TeamModification.POKEMON,
                TeamModification.EVS,
                TeamModification.ABILITIES,
                TeamModification.MOVES,
                TeamModification.ITEMS,
            }
        ),
        level_cap=57,
    )
    monkeypatch.setattr(service_module, "create_emulator", lambda task: emulator)

    party_memory.load_u32(BATTLE_TYPE_FLAGS, 1)
    service = BattleService(task)
    service.session = BattleSession(emu=emulator, party=Party(emulator.mem))
    trial = Trial(
        task=task,
        max_episodes=2,
        trajectory_path=tmp_path / "trajectory.jsonl",
        score_path=tmp_path / "score.json",
    )

    result = trial.handle(
        {
            "verb": "apply-team",
            "team": {
                "members": [
                    {
                        "slot": 0,
                        "species_id": 25,
                        "evs": {"HP": 0, "ATK": 0, "DEF": 0, "SPE": 0, "SPA": 0, "SPDEF": 0},
                        "ability_id": 9,
                        "move_ids": [85, 97, 423, 743],
                        "held_item_id": 0,
                    },
                    {
                        "slot": 1,
                        "species_id": 944,
                        "evs": {"HP": 0, "ATK": 0, "DEF": 0, "SPE": 0, "SPA": 0, "SPDEF": 0},
                        "ability_id": 66,
                        "move_ids": [365, 53, 126, 434],
                        "held_item_id": 0,
                    },
                ]
            },
        },
        service,
    )

    assert result["ok"] is True
    assert trial.episodes == 2
    assert result["team"]["members"][0]["name"] == "Pikachu"
    assert result["team"]["members"][0]["stats"] == {
        "HP": 95,
        "ATK": 60,
        "DEF": 35,
        "SPE": 95,
        "SPA": 55,
        "SPDEF": 45,
    }
    assert Party(emulator.mem).members[0].species_id == 25
    assert Party(emulator.mem).members[0].name == "Pikachu"
    assert Party(emulator.mem).members[0].ability_id == 9
    assert Party(emulator.mem).members[0].move_ids == (85, 97, 423, 743)
    assert party_memory.read(PARTY_BASE_ADDR + 0x08, 10) == bytes(
        [0xCA, 0xDD, 0xDF, 0xD5, 0xD7, 0xDC, 0xE9, 0xFF, 0xFF, 0xFF]
    )
    assert party_memory.u32[PARTY_BASE_ADDR + 0x24] == 50 ** 3

    service.reset()

    assert Party(emulator.mem).members[0].species_id == 25
    assert Party(emulator.mem).members[0].name == "Pikachu"


def test_trial_rejects_invalid_pokemon_id_without_advancing_episode(
    monkeypatch,
    party_memory,
    tmp_path,
) -> None:
    emulator = FakeEmulator(party_memory)
    task = TaskSpec(
        id="test",
        rom_path=Path("test.gba"),
        save_state_path=Path("test.ss0"),
        allowed_team_modifications=frozenset({TeamModification.POKEMON}),
        level_cap=57,
    )
    monkeypatch.setattr(service_module, "create_emulator", lambda task: emulator)

    party_memory.load_u32(BATTLE_TYPE_FLAGS, 1)
    service = BattleService(task)
    service.session = BattleSession(emu=emulator, party=Party(emulator.mem))
    before_memory = party_memory.snapshot()
    before_team = service.team()
    trial = Trial(
        task=task,
        max_episodes=2,
        trajectory_path=tmp_path / "trajectory.jsonl",
        score_path=tmp_path / "score.json",
    )

    result = trial.handle(
        {
            "verb": "apply-team",
            "team": {
                "members": [
                    {"slot": 0, "species_id": 0},
                    {"slot": 1, "species_id": 944},
                ]
            },
        },
        service,
    )

    assert result == {"ok": False, "error": "species_id must be a valid Pokemon ID"}
    assert trial.episodes == 1
    assert service.active_team_config is None
    assert party_memory.snapshot() == before_memory
    assert service.team() == before_team


def test_trial_rejects_incineroar_above_level_cap_without_advancing_episode(
    monkeypatch,
    party_memory,
    tmp_path,
) -> None:
    emulator = FakeEmulator(party_memory)
    task = TaskSpec(
        id="test",
        rom_path=Path("test.gba"),
        save_state_path=Path("test.ss0"),
        allowed_team_modifications=frozenset({TeamModification.POKEMON}),
        level_cap=30,
    )
    monkeypatch.setattr(service_module, "create_emulator", lambda task: emulator)

    party_memory.load_u32(BATTLE_TYPE_FLAGS, 1)
    service = BattleService(task)
    service.session = BattleSession(emu=emulator, party=Party(emulator.mem))
    before_memory = party_memory.snapshot()
    before_team = service.team()
    trial = Trial(
        task=task,
        max_episodes=2,
        trajectory_path=tmp_path / "trajectory.jsonl",
        score_path=tmp_path / "score.json",
    )

    result = trial.handle(
        {
            "verb": "apply-team",
            "team": {
                "members": [
                    {"slot": 0, "species_id": 1},
                    {"slot": 1, "species_id": 944},
                ]
            },
        },
        service,
    )

    assert result == {
        "ok": False,
        "error": "species_id must be available at the task level cap",
    }
    assert trial.episodes == 1
    assert service.active_team_config is None
    assert party_memory.snapshot() == before_memory
    assert service.team() == before_team


def test_trial_validates_abilities_against_replacement_pokemon(
    monkeypatch,
    party_memory,
    tmp_path,
) -> None:
    emulator = FakeEmulator(party_memory)
    task = TaskSpec(
        id="test",
        rom_path=Path("test.gba"),
        save_state_path=Path("test.ss0"),
        allowed_team_modifications=frozenset(
            {TeamModification.POKEMON, TeamModification.ABILITIES}
        ),
        level_cap=57,
    )
    monkeypatch.setattr(service_module, "create_emulator", lambda task: emulator)

    party_memory.load_u32(BATTLE_TYPE_FLAGS, 1)
    service = BattleService(task)
    service.session = BattleSession(emu=emulator, party=Party(emulator.mem))
    before_memory = party_memory.snapshot()
    trial = Trial(
        task=task,
        max_episodes=2,
        trajectory_path=tmp_path / "trajectory.jsonl",
        score_path=tmp_path / "score.json",
    )

    result = trial.handle(
        {
            "verb": "apply-team",
            "team": {
                "members": [
                    {"slot": 0, "species_id": 25, "ability_id": 34},
                    {"slot": 1, "species_id": 944, "ability_id": 66},
                ]
            },
        },
        service,
    )

    assert result == {
        "ok": False,
        "error": "ability_id must be a valid ability for the active Pokemon",
    }
    assert trial.episodes == 1
    assert service.active_team_config is None
    assert party_memory.snapshot() == before_memory


@pytest.mark.parametrize("held_item_id", [-1, 750, "711"])
def test_trial_rejects_invalid_held_items_without_advancing_episode(
    monkeypatch,
    party_memory,
    tmp_path,
    held_item_id,
) -> None:
    emulator = FakeEmulator(party_memory)
    task = TaskSpec(
        id="test",
        rom_path=Path("test.gba"),
        save_state_path=Path("test.ss0"),
        allowed_team_modifications=frozenset({TeamModification.ITEMS}),
        level_cap=100,
    )
    monkeypatch.setattr(service_module, "create_emulator", lambda task: emulator)

    party_memory.load_u32(BATTLE_TYPE_FLAGS, 1)
    service = BattleService(task)
    service.session = BattleSession(emu=emulator, party=Party(emulator.mem))
    before_memory = party_memory.snapshot()
    before_team = service.team()
    trial = Trial(
        task=task,
        max_episodes=2,
        trajectory_path=tmp_path / "trajectory.jsonl",
        score_path=tmp_path / "score.json",
    )
    team_payload = {
        "members": [
            {"slot": 0, "species_id": 1, "held_item_id": held_item_id},
            {"slot": 1, "species_id": 944, "held_item_id": 695},
        ]
    }

    result = trial.handle({"verb": "apply-team", "team": team_payload}, service)

    assert result == {"ok": False, "error": "held_item_id must be a valid item ID"}
    assert trial.episodes == 1
    assert service.active_team_config is None
    assert party_memory.snapshot() == before_memory
    assert service.team() == before_team


def test_trial_rejects_moves_above_level_cap_without_advancing_episode(
    monkeypatch,
    party_memory,
    tmp_path,
) -> None:
    emulator = FakeEmulator(party_memory)
    task = TaskSpec(
        id="test",
        rom_path=Path("test.gba"),
        save_state_path=Path("test.ss0"),
        allowed_team_modifications=frozenset({TeamModification.MOVES}),
        level_cap=57,
    )
    monkeypatch.setattr(service_module, "create_emulator", lambda task: emulator)

    party_memory.load_u32(BATTLE_TYPE_FLAGS, 1)
    service = BattleService(task)
    service.session = BattleSession(emu=emulator, party=Party(emulator.mem))
    before_memory = party_memory.snapshot()
    before_team = service.team()
    trial = Trial(
        task=task,
        max_episodes=2,
        trajectory_path=tmp_path / "trajectory.jsonl",
        score_path=tmp_path / "score.json",
    )

    result = trial.handle(
        {
            "verb": "apply-team",
            "team": {
                "members": [
                    {"slot": 0, "species_id": 1, "move_ids": [33, 45, 73, 345]},
                    {"slot": 1, "species_id": 944, "move_ids": [365, 53, 126, 147]},
                ]
            },
        },
        service,
    )

    assert result == {
        "ok": False,
        "error": "each move_id must be learnable by the active Pokemon at the task level cap",
    }
    assert trial.episodes == 1
    assert service.active_team_config is None
    assert party_memory.snapshot() == before_memory
    assert service.team() == before_team


def test_trial_applies_valid_natures_without_changing_abilities(
    monkeypatch, party_memory, tmp_path
) -> None:
    emulator = FakeEmulator(party_memory)
    task = TaskSpec(
        id="test",
        rom_path=Path("test.gba"),
        save_state_path=Path("test.ss0"),
        allowed_team_modifications=frozenset({TeamModification.NATURES}),
        level_cap=100,
    )
    monkeypatch.setattr(service_module, "create_emulator", lambda task: emulator)
    party_memory.load_u32(BATTLE_TYPE_FLAGS, 1)
    service = BattleService(task)
    service.session = BattleSession(emu=emulator, party=Party(emulator.mem))
    original_team = service.original_team_config
    trial = Trial(
        task=task,
        max_episodes=2,
        trajectory_path=tmp_path / "trajectory.jsonl",
        score_path=tmp_path / "score.json",
    )

    result = trial.handle(
        {
            "verb": "apply-team",
            "team": {
                "members": [
                    {"slot": 0, "species_id": 1, "nature_id": 3},
                    {"slot": 1, "species_id": 944, "nature_id": 15},
                ]
            },
        },
        service,
    )

    assert result["ok"] is True
    assert trial.episodes == 2
    assert result["team"]["members"][0]["nature"] == {"id": 3, "name": "Adamant"}
    assert result["team"]["members"][1]["nature"] == {"id": 15, "name": "Modest"}
    assert result["team"]["members"][0]["stats"] == {
        "HP": 105, "ATK": 59, "DEF": 54, "SPE": 50, "SPA": 63, "SPDEF": 70,
    }
    assert result["team"]["members"][1]["stats"] == {
        "HP": 155, "ATK": 108, "DEF": 95, "SPE": 65, "SPA": 93, "SPDEF": 95,
    }
    active_team = service.active_team_config
    assert active_team is not None
    for original_member, active_member in zip(original_team.members, active_team.members):
        assert active_member.ability_id == original_member.ability_id
        assert active_member.evs == original_member.evs
        assert active_member.move_ids == original_member.move_ids
        assert active_member.held_item == original_member.held_item


@pytest.mark.parametrize("invalid_nature_id", [-1, 25, True, "3"])
def test_trial_rejects_invalid_natures_without_advancing_episode(
    monkeypatch, party_memory, tmp_path, invalid_nature_id
) -> None:
    emulator = FakeEmulator(party_memory)
    task = TaskSpec(
        id="test",
        rom_path=Path("test.gba"),
        save_state_path=Path("test.ss0"),
        allowed_team_modifications=frozenset({TeamModification.NATURES}),
        level_cap=100,
    )
    monkeypatch.setattr(service_module, "create_emulator", lambda task: emulator)
    party_memory.load_u32(BATTLE_TYPE_FLAGS, 1)
    service = BattleService(task)
    service.session = BattleSession(emu=emulator, party=Party(emulator.mem))
    before_memory = party_memory.snapshot()
    before_team = service.team()
    trial = Trial(
        task=task,
        max_episodes=2,
        trajectory_path=tmp_path / "trajectory.jsonl",
        score_path=tmp_path / "score.json",
    )

    result = trial.handle(
        {
            "verb": "apply-team",
            "team": {
                "members": [
                    {"slot": 0, "species_id": 1, "nature_id": invalid_nature_id},
                    {"slot": 1, "species_id": 944, "nature_id": 15},
                ]
            },
        },
        service,
    )

    assert result == {
        "ok": False,
        "error": "nature_id must be an integer from 0 through 24",
    }
    assert trial.episodes == 1
    assert service.active_team_config is None
    assert party_memory.snapshot() == before_memory
    assert service.team() == before_team


def test_trial_rejects_natures_when_only_abilities_are_allowed(
    monkeypatch, party_memory, tmp_path
) -> None:
    emulator = FakeEmulator(party_memory)
    task = TaskSpec(
        id="test",
        rom_path=Path("test.gba"),
        save_state_path=Path("test.ss0"),
        allowed_team_modifications=frozenset({TeamModification.ABILITIES}),
        level_cap=100,
    )
    monkeypatch.setattr(service_module, "create_emulator", lambda task: emulator)
    party_memory.load_u32(BATTLE_TYPE_FLAGS, 1)
    service = BattleService(task)
    service.session = BattleSession(emu=emulator, party=Party(emulator.mem))
    trial = Trial(
        task=task,
        max_episodes=2,
        trajectory_path=tmp_path / "trajectory.jsonl",
        score_path=tmp_path / "score.json",
    )

    result = trial.handle(
        {
            "verb": "apply-team",
            "team": {
                "members": [
                    {"slot": 0, "species_id": 1, "nature_id": 3},
                    {"slot": 1, "species_id": 944, "nature_id": 15},
                ]
            },
        },
        service,
    )

    assert result == {
        "ok": False,
        "error": "updating Natures is not allowed for this task",
    }
    assert trial.episodes == 1
    assert service.active_team_config is None


def test_trial_rejects_ability_not_available_to_species_without_advancing_episode(
    monkeypatch,
    party_memory,
    tmp_path,
) -> None:
    emulator = FakeEmulator(party_memory)
    task = TaskSpec(
        id="test",
        rom_path=Path("test.gba"),
        save_state_path=Path("test.ss0"),
        allowed_team_modifications=frozenset({TeamModification.ABILITIES}),
        level_cap=100,
    )
    monkeypatch.setattr(service_module, "create_emulator", lambda task: emulator)

    party_memory.load_u32(BATTLE_TYPE_FLAGS, 1)
    service = BattleService(task)
    service.session = BattleSession(emu=emulator, party=Party(emulator.mem))
    before_memory = party_memory.snapshot()
    before_team = service.team()
    trial = Trial(
        task=task,
        max_episodes=2,
        trajectory_path=tmp_path / "trajectory.jsonl",
        score_path=tmp_path / "score.json",
    )

    result = trial.handle(
        {
            "verb": "apply-team",
            "team": {
                "members": [
                    {"slot": 0, "species_id": 1, "ability_id": 66},
                    {"slot": 1, "species_id": 944, "ability_id": 66},
                ]
            },
        },
        service,
    )

    assert result == {
        "ok": False,
        "error": "ability_id must be a valid ability for the active Pokemon",
    }
    assert trial.episodes == 1
    assert service.active_team_config is None
    assert party_memory.snapshot() == before_memory
    assert service.team() == before_team


@pytest.mark.parametrize(
    ("invalid_evs", "error"),
    [
        (
            {"HP": 252, "ATK": 252, "DEF": 8, "SPE": 0, "SPA": 0, "SPDEF": 0},
            "each Pokemon may have at most 508 total EVs",
        ),
        (
            {"HP": 256, "ATK": 0, "DEF": 0, "SPE": 0, "SPA": 0, "SPDEF": 0},
            "EVs must be integers from 0 through 252 in multiples of four",
        ),
    ],
)
def test_trial_rejects_invalid_ev_spreads_without_advancing_episode(
    monkeypatch,
    party_memory,
    tmp_path,
    invalid_evs,
    error,
) -> None:
    emulator = FakeEmulator(party_memory)
    task = TaskSpec(
        id="test",
        rom_path=Path("test.gba"),
        save_state_path=Path("test.ss0"),
        allowed_team_modifications=frozenset({TeamModification.EVS}),
        level_cap=100,
    )
    monkeypatch.setattr(service_module, "create_emulator", lambda task: emulator)

    party_memory.load_u32(BATTLE_TYPE_FLAGS, 1)
    service = BattleService(task)
    service.session = BattleSession(emu=emulator, party=Party(emulator.mem))
    before_memory = party_memory.snapshot()
    before_team = service.team()
    trial = Trial(
        task=task,
        max_episodes=2,
        trajectory_path=tmp_path / "trajectory.jsonl",
        score_path=tmp_path / "score.json",
    )
    team_payload = {
        "members": [
            {"slot": 0, "species_id": 1, "evs": invalid_evs},
            {
                "slot": 1,
                "species_id": 944,
                "evs": {"HP": 252, "ATK": 252, "DEF": 4, "SPE": 0, "SPA": 0, "SPDEF": 0},
            },
        ]
    }

    result = trial.handle({"verb": "apply-team", "team": team_payload}, service)

    assert result == {"ok": False, "error": error}
    assert trial.episodes == 1
    assert service.active_team_config is None
    assert party_memory.snapshot() == before_memory
    assert service.team() == before_team


def test_trial_rejects_team_optimization_when_task_does_not_allow_it(
    monkeypatch,
    party_memory,
    tmp_path,
) -> None:
    emulator = FakeEmulator(party_memory)
    task = TaskSpec(
        id="test",
        rom_path=Path("test.gba"),
        save_state_path=Path("test.ss0"),
        allowed_team_modifications=frozenset(),
        level_cap=100,
    )
    monkeypatch.setattr(service_module, "create_emulator", lambda task: emulator)
    service = BattleService(task)
    service.active_team_config = service.original_team_config
    party_memory.load_u32(BATTLE_TYPE_FLAGS, 1)
    service.session = BattleSession(emu=emulator, party=Party(emulator.mem))
    before_team = service.team()
    trial = Trial(
        task=task,
        max_episodes=2,
        trajectory_path=tmp_path / "trajectory.jsonl",
        score_path=tmp_path / "score.json",
    )
    team_payload = {
        "members": [
            {
                "slot": 0,
                "species_id": 1,
                "evs": {"HP": 252, "ATK": 0, "DEF": 4, "SPE": 0, "SPA": 0, "SPDEF": 252},
            },
            {
                "slot": 1,
                "species_id": 944,
                "evs": {"HP": 252, "ATK": 252, "DEF": 4, "SPE": 0, "SPA": 0, "SPDEF": 0},
            },
        ]
    }

    result = trial.handle({"verb": "apply-team", "team": team_payload}, service)

    assert result == {"ok": False, "error": "team updates are not allowed for this task"}
    assert trial.episodes == 1
    assert service.active_team_config is service.original_team_config
    assert service.team() == before_team


def test_trial_requires_and_applies_initial_team_without_consuming_episode(
    monkeypatch,
    party_memory,
    tmp_path,
) -> None:
    emulator = FakeEmulator(party_memory)
    task = TaskSpec(
        id="test",
        rom_path=Path("test.gba"),
        save_state_path=Path("test.ss0"),
        allowed_team_modifications=frozenset(),
        level_cap=57,
        team_size=2,
    )
    monkeypatch.setattr(service_module, "create_emulator", lambda task: emulator)
    service = BattleService(task)
    trial = Trial(
        task=task,
        max_episodes=1,
        trajectory_path=tmp_path / "trajectory.jsonl",
        score_path=tmp_path / "score.json",
    )
    team_payload = {
        "members": [
            {
                "slot": 0,
                "species_id": 1,
                "ability_id": 34,
                "move_ids": [33, 45, 73, 345],
                "held_item_id": 0,
                "evs": {"HP": 252, "ATK": 0, "DEF": 4, "SPE": 0, "SPA": 0, "SPDEF": 252},
            },
            {
                "slot": 1,
                "species_id": 944,
                "ability_id": 66,
                "move_ids": [365, 53, 126, 434],
                "held_item_id": 711,
                "evs": {"HP": 252, "ATK": 252, "DEF": 4, "SPE": 0, "SPA": 0, "SPDEF": 0},
            },
        ]
    }

    assert service.observe() == {
        "ok": True,
        "observation": {"phase": "awaiting_team", "level_cap": 57, "team_size": 2},
    }
    assert service.team() == {"ok": True, "configured": False, "team_size": 2, "level_cap": 57}
    assert service.lead("Bulbasaur") == {
        "ok": False,
        "error": "apply-team must configure a valid team before lead",
    }

    invalid_result = trial.handle(
        {
            "verb": "apply-team",
            "team": {
                "members": [
                    dict(team_payload["members"][0], unexpected=True),
                    team_payload["members"][1],
                ]
            },
        },
        service,
    )

    assert invalid_result["ok"] is False
    assert service.active_team_config is None
    assert trial.episodes == 1

    result = trial.handle({"verb": "apply-team", "team": team_payload}, service)

    assert result["ok"] is True
    assert result["observation"]["phase"] == "no_battle"
    assert trial.episodes == 1
    assert service.active_team_config is not None
    assert [member.level for member in service.active_team_config.members] == [57, 57]
    assert [member.nature_id for member in service.active_team_config.members] == [0, 0]
    assert service.team()["configured"] is True
