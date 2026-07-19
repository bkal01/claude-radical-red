import importlib
import sys
from types import ModuleType, SimpleNamespace

import pytest

from rrbench.tasks import TeamModification
from rrbench.team import PokemonConfig, TeamConfig


EVS = {"HP": 0, "ATK": 0, "DEF": 0, "SPE": 0, "SPA": 0, "SPDEF": 0}


@pytest.fixture
def service_module(monkeypatch: pytest.MonkeyPatch):
    emulator_module = ModuleType("rrbench.emulator.emulator")
    emulator_module.Emulator = object
    for key in ("KEY_A", "KEY_B", "KEY_UP", "KEY_DOWN", "KEY_LEFT", "KEY_RIGHT"):
        setattr(emulator_module, key, 0)

    module_names = (
        "rrbench.interface.service",
        "rrbench.battle.engine",
        "rrbench.battle.state",
        "rrbench.battle.capture",
    )
    saved_modules = {name: sys.modules.get(name) for name in module_names}
    for name in module_names:
        sys.modules.pop(name, None)
    monkeypatch.setitem(sys.modules, "rrbench.emulator.emulator", emulator_module)

    try:
        yield importlib.import_module("rrbench.interface.service")
    finally:
        for name in module_names:
            sys.modules.pop(name, None)
            if saved_modules[name] is not None:
                sys.modules[name] = saved_modules[name]


def make_service(service_module, modifications, session) -> object:
    service = object.__new__(service_module.BattleService)
    service.task = SimpleNamespace(allowed_team_modifications=frozenset(modifications))
    service.session = session
    service.emu = SimpleNamespace(mem=object())
    service.original_team_config = TeamConfig(
        members=[
            PokemonConfig(
                species_id=1,
                evs=dict(EVS),
                level=50,
                nature_id=0,
                ability_id=34,
                held_item=7,
                move_ids=(1, 2, 0, 0),
            ),
            PokemonConfig(
                species_id=2,
                evs=dict(EVS),
                level=50,
                nature_id=0,
                ability_id=0,
                held_item=0,
                move_ids=(3, 0, 0, 0),
            ),
        ]
    )
    service.active_team_config = None
    return service


def make_payload(entries: list[tuple[int, int, int]]) -> dict:
    return {
        "members": [
            {
                "slot": slot,
                "species_id": species_id,
                "evs": {**EVS, "HP": hp},
            }
            for slot, species_id, hp in entries
        ]
    }


@pytest.mark.parametrize("ended", [False, True])
def test_apply_team_accepts_a_live_battle_or_loss_and_member_reordering(
    service_module, monkeypatch: pytest.MonkeyPatch, ended: bool
) -> None:
    monkeypatch.setattr(service_module, "in_battle", lambda mem: True)
    service = make_service(
        service_module,
        {TeamModification.EVS},
        SimpleNamespace(ended=ended, won=False),
    )

    result = service.apply_team(make_payload([(1, 2, 252), (0, 1, 4)]))

    assert result["ok"] is True
    assert [member.species_id for member in service.active_team_config.members] == [1, 2]
    assert [member.evs["HP"] for member in service.active_team_config.members] == [4, 252]


def test_team_returns_the_active_config_and_calculated_stats(service_module) -> None:
    service = make_service(
        service_module,
        {TeamModification.EVS},
        SimpleNamespace(ended=False, won=False),
    )
    service.active_team_config = TeamConfig(
        members=[
            PokemonConfig(
                species_id=1,
                evs={**EVS, "HP": 252},
                level=50,
                nature_id=0,
                ability_id=34,
                held_item=7,
                move_ids=(1, 2, 0, 0),
            ),
            PokemonConfig(
                species_id=2,
                evs=dict(EVS),
                level=50,
                nature_id=0,
                ability_id=0,
                held_item=0,
                move_ids=(3, 0, 0, 0),
            ),
        ]
    )

    result = service.team()

    assert result["ok"] is True
    assert result["team"]["members"][0] == {
        "slot": 0,
        "species_id": 1,
        "name": "Bulbasaur",
        "types": ["Grass", "Poison"],
        "level": 50,
        "nature": {"id": 0, "name": "Hardy"},
        "ability_id": 34,
        "ability": "Chlorophyll",
        "held_item_id": 7,
        "moves": [
            {"slot": 0, "move_id": 1, "name": "Pound"},
            {"slot": 1, "move_id": 2, "name": "Karate Chop"},
            {"slot": 2, "move_id": 0, "name": ""},
            {"slot": 3, "move_id": 0, "name": ""},
        ],
        "evs": {**EVS, "HP": 252},
        "stats": {"HP": 136, "ATK": 54, "DEF": 54, "SPE": 50, "SPA": 70, "SPDEF": 70},
    }


def test_apply_team_rejects_a_species_mismatch_without_changing_config(service_module) -> None:
    service = make_service(
        service_module,
        {TeamModification.EVS},
        SimpleNamespace(ended=True, won=False),
    )
    existing_config = TeamConfig(
        members=[
            PokemonConfig(species_id=3, evs=dict(EVS)),
            PokemonConfig(species_id=2, evs=dict(EVS)),
        ]
    )
    service.active_team_config = existing_config

    result = service.apply_team(make_payload([(0, 2, 0), (1, 2, 0)]))

    assert result == {"ok": False, "error": "species_id must match the active team member at its slot"}
    assert service.active_team_config is existing_config


def test_apply_team_rejects_invalid_ev_values_without_changing_config(service_module) -> None:
    service = make_service(
        service_module,
        {TeamModification.EVS},
        SimpleNamespace(ended=True, won=False),
    )
    payload = make_payload([(0, 1, 254), (1, 2, 0)])

    result = service.apply_team(payload)

    assert result == {
        "ok": False,
        "error": "EVs must be integers from 0 through 252 in multiples of four",
    }
    assert service.active_team_config is None


@pytest.mark.parametrize(
    ("modifications", "error"),
    [
        (set(), "team updates are not allowed for this task"),
        ({"other"}, "updating EVs is not allowed for this task"),
    ],
)
def test_apply_team_enforces_task_capabilities(service_module, modifications, error) -> None:
    service = make_service(
        service_module,
        modifications,
        SimpleNamespace(ended=True, won=False),
    )

    result = service.apply_team(make_payload([(0, 1, 0), (1, 2, 0)]))

    assert result == {"ok": False, "error": error}
