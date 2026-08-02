from pathlib import Path

import pytest

from rrbench.battle.addresses import BATTLE_TYPE_FLAGS
from rrbench.battle.state import BattleSession
from rrbench.emulator.memory import Party
from rrbench.harness.trial import Trial
from rrbench.interface import service as service_module
from rrbench.interface.service import BattleService
from rrbench.tasks import TaskSpec, TeamModification
from tests.support.fakes import FakeEmulator


def test_trial_applies_valid_ev_spreads(monkeypatch, party_memory, tmp_path) -> None:
    emulator = FakeEmulator(party_memory)
    task = TaskSpec(
        id="test",
        rom_path=Path("test.gba"),
        save_state_path=Path("test.ss0"),
        allowed_team_modifications=frozenset({TeamModification.EVS}),
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
    assert result["observation"]["phase"] == "no_battle"
    assert trial.episodes == 2

    active_team = service.active_team_config
    assert active_team is not None
    observation_result = service.observe()
    assert observation_result == {
        "ok": True,
        "observation": {
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
        },
    }
    assert result["observation"] == observation_result["observation"]
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
    )
    monkeypatch.setattr(service_module, "create_emulator", lambda task: emulator)
    service = BattleService(task)
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
    assert service.active_team_config is None
    assert service.team() == before_team
