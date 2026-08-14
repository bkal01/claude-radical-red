from pathlib import Path

import pytest

from rrbench.battle.addresses import (
    BATTLE_MONS_BASE,
    BATTLE_TERRAIN,
    BATTLE_TYPE_FLAGS,
    BATTLE_WEATHER,
    MON_ABILITY,
    MON_CUR_HP,
    MON_MAX_HP,
    MON_SPECIES,
    MON_STAT_STAGES,
    OPP_MON_BASE,
    SIDE_STATUS_OPP,
    SIDE_STATUS_PLAYER,
    TERRAIN_TIMER,
)
from rrbench.battle.capture import MessageEvent
from rrbench.battle.state import BattleSession, StepLog, read_battle_state
from rrbench.emulator.memory import PARTY_BASE_ADDR, SLOT_SIZE, Party
from rrbench.interface import service as service_module
from rrbench.interface.service import BattleService
from rrbench.tasks import TaskSpec
from tests.support.fakes import FakeEmulator


@pytest.fixture
def live_battle_service(monkeypatch, party_memory):
    emulator = FakeEmulator(party_memory)
    task = TaskSpec(
        id="test",
        rom_path=Path("test.gba"),
        save_state_path=Path("test.ss0"),
        allowed_team_modifications=frozenset(),
        level_cap=100,
    )
    monkeypatch.setattr(service_module, "create_emulator", lambda task: emulator)

    party_memory.load_u32(BATTLE_TYPE_FLAGS, 1)
    party_memory.load_u16(BATTLE_MONS_BASE + MON_SPECIES, 1)
    party_memory.load_u16(BATTLE_MONS_BASE + MON_CUR_HP, 100)
    party_memory.load_u16(BATTLE_MONS_BASE + MON_MAX_HP, 120)
    party_memory.load_bytes(
        BATTLE_MONS_BASE + MON_STAT_STAGES,
        bytes((6, 6, 6, 6, 6, 6, 6)),
    )
    party_memory.load_u16(OPP_MON_BASE + MON_SPECIES, 2)
    party_memory.load_u8(OPP_MON_BASE + MON_ABILITY, 34)
    party_memory.load_u16(OPP_MON_BASE + MON_CUR_HP, 71)
    party_memory.load_u16(OPP_MON_BASE + MON_MAX_HP, 100)
    party_memory.load_bytes(
        OPP_MON_BASE + MON_STAT_STAGES,
        bytes((6, 6, 6, 6, 6, 6, 6)),
    )
    party_memory.load_u32(BATTLE_WEATHER, 0)
    party_memory.load_u8(BATTLE_TERRAIN, 0)
    party_memory.load_u8(TERRAIN_TIMER, 0)
    party_memory.load_u8(SIDE_STATUS_PLAYER, 0)
    party_memory.load_u8(SIDE_STATUS_OPP, 0)

    service = BattleService(task)
    service.session = BattleSession(emu=emulator, party=Party(emulator.mem))
    return service, emulator


def test_lead_starts_battle_with_valid_party_member(monkeypatch, party_memory) -> None:
    emulator = FakeEmulator(party_memory)
    task = TaskSpec(
        id="test",
        rom_path=Path("test.gba"),
        save_state_path=Path("test.ss0"),
        allowed_team_modifications=frozenset(),
        level_cap=100,
    )
    monkeypatch.setattr(service_module, "create_emulator", lambda task: emulator)

    def scripted_start_battle(current_emulator, party, lead):
        assert current_emulator is emulator
        assert party.names == ["Bulbasaur", "Incineroar"]
        assert lead == "Incineroar"

        party.set_lead(lead)
        party.refresh()
        current_emulator.mem.load_u32(BATTLE_TYPE_FLAGS, 1)
        current_emulator.mem.load_u16(BATTLE_MONS_BASE + MON_SPECIES, 944)
        current_emulator.mem.load_u16(BATTLE_MONS_BASE + MON_CUR_HP, 150)
        current_emulator.mem.load_u16(BATTLE_MONS_BASE + MON_MAX_HP, 150)
        current_emulator.mem.load_bytes(
            BATTLE_MONS_BASE + MON_STAT_STAGES,
            bytes((6, 6, 6, 6, 6, 6, 6)),
        )
        current_emulator.mem.load_u16(OPP_MON_BASE + MON_SPECIES, 2)
        current_emulator.mem.load_u8(OPP_MON_BASE + MON_ABILITY, 34)
        current_emulator.mem.load_u16(OPP_MON_BASE + MON_CUR_HP, 71)
        current_emulator.mem.load_u16(OPP_MON_BASE + MON_MAX_HP, 100)
        current_emulator.mem.load_bytes(
            OPP_MON_BASE + MON_STAT_STAGES,
            bytes((6, 6, 6, 6, 6, 6, 6)),
        )
        current_emulator.mem.load_u32(BATTLE_WEATHER, 0)
        current_emulator.mem.load_u8(BATTLE_TERRAIN, 0)
        current_emulator.mem.load_u8(TERRAIN_TIMER, 0)
        current_emulator.mem.load_u8(SIDE_STATUS_PLAYER, 0)
        current_emulator.mem.load_u8(SIDE_STATUS_OPP, 0)

        state = read_battle_state(current_emulator.mem, party)
        session = BattleSession(emu=current_emulator, party=party)
        messages = [MessageEvent("Go, Incineroar!", {}, None, "")]
        return session, state, messages

    monkeypatch.setattr(service_module, "start_battle", scripted_start_battle)
    service = BattleService(task)
    service.active_team_config = service.original_team_config

    result = service.lead("Incineroar")

    assert result == {
        "ok": True,
        "messages": ["Go, Incineroar!"],
        "observation": {
            "phase": "in_battle",
            "needs_replacement": False,
            "active": {"name": "Incineroar", "form": None, "slot": 0},
            "party": [
                {
                    "name": "Incineroar",
                    "form": None,
                    "current_hp": 88,
                    "max_hp": 150,
                    "status": None,
                    "active": True,
                    "fainted": False,
                    "moves": [
                        {"name": "Ember", "pp_remaining": 20},
                        {"name": "Growl", "pp_remaining": 15},
                    ],
                },
                {
                    "name": "Bulbasaur",
                    "form": None,
                    "current_hp": 100,
                    "max_hp": 120,
                    "status": "poison",
                    "active": False,
                    "fainted": False,
                    "moves": [
                        {"name": "Pound", "pp_remaining": 10},
                        {"name": "Growl", "pp_remaining": 12},
                    ],
                },
            ],
            "opponent": {
                "species": "Ivysaur",
                "form": None,
                "species_id": 2,
                "ability": "Chlorophyll",
                "current_hp": 71,
                "max_hp": 100,
            },
            "weather": {"kind": "none", "turns_left": "inf"},
            "terrain": {"kind": "none", "turns_left": 0},
            "hazards": {
                "player": {"stealth_rock": False, "spikes": 0, "toxic_spikes": 0},
                "opponent": {"stealth_rock": False, "spikes": 0, "toxic_spikes": 0},
            },
            "stat_stages": {
                "player": {
                    "ATK": 0,
                    "DEF": 0,
                    "SPE": 0,
                    "SPA": 0,
                    "SPD": 0,
                    "ACC": 0,
                    "EVA": 0,
                },
                "opponent": {
                    "ATK": 0,
                    "DEF": 0,
                    "SPE": 0,
                    "SPA": 0,
                    "SPD": 0,
                    "ACC": 0,
                    "EVA": 0,
                },
            },
        },
        "ended": False,
        "won": False,
    }


def test_lead_rejects_absent_pokemon_and_live_battle(monkeypatch, party_memory) -> None:
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

    absent_result = service.lead("Pikachu")

    assert absent_result == {
        "ok": False,
        "error": "'Pikachu' is not in your party. Available Pokemon: Bulbasaur, Incineroar. Choose one of these, or change your team.",
    }
    assert service.session is None

    party_memory.load_u32(BATTLE_TYPE_FLAGS, 1)

    live_battle_result = service.lead("Bulbasaur")

    assert live_battle_result == {
        "ok": False,
        "error": "lead is only valid in no_battle phase",
    }
    assert service.session is None


def test_set_lead_targets_the_requested_pokemon_form(party_memory) -> None:
    party_memory.load_u16(PARTY_BASE_ADDR + 0x20, 714)
    party_memory.load_u16(PARTY_BASE_ADDR + SLOT_SIZE + 0x20, 715)
    party = Party(party_memory)

    party.set_lead("Rotom-frost")

    assert [pokemon.label for pokemon in party.members] == [
        "Rotom-frost",
        "Rotom-wash",
    ]
    assert [
        party_memory.u16[PARTY_BASE_ADDR + slot * SLOT_SIZE + 0x20]
        for slot in range(2)
    ] == [715, 714]


def test_fight_accepts_move_known_by_active_pokemon(monkeypatch, live_battle_service) -> None:
    service, emulator = live_battle_service
    action_calls = []

    def scripted_do_action(current_emulator, party, session, action_type, action_arg):
        action_calls.append((current_emulator, party, session, action_type, action_arg))
        state = read_battle_state(current_emulator.mem, party)
        step_log = StepLog(
            step=1,
            action="FIGHT Pound",
            opponent_move=0,
            hp_snapshot=tuple((p.current_hp, p.max_hp) for p in party.members),
            messages=[MessageEvent("Pound landed!", {}, None, "")],
        )
        return session, state, step_log

    monkeypatch.setattr(service_module, "do_action", scripted_do_action)

    result = service.action("FIGHT Pound")

    assert len(action_calls) == 1
    assert action_calls[0][0] is emulator
    assert action_calls[0][3:] == ("FIGHT", "Pound")
    assert result["ok"] is True
    assert result["messages"] == ["Pound landed!"]
    assert result["observation"]["phase"] == "in_battle"
    assert result["observation"]["active"] == {
        "name": "Bulbasaur",
        "form": None,
        "slot": 0,
    }
    assert result["observation"]["party"][0]["moves"] == [
        {"name": "Pound", "pp_remaining": 10},
        {"name": "Growl", "pp_remaining": 12},
    ]
    assert result["ended"] is False
    assert result["won"] is False


def test_fight_rejects_move_outside_active_pokemon_movepool(live_battle_service) -> None:
    service, emulator = live_battle_service

    result = service.action("FIGHT Tackle")

    assert result == {
        "ok": False,
        "error": "Bulbasaur does not know 'Tackle'",
    }
    assert emulator.calls == []


def test_fight_rejects_move_with_zero_pp(live_battle_service, party_memory) -> None:
    service, emulator = live_battle_service
    party_memory.load_u8(PARTY_BASE_ADDR + 0x34, 0)

    result = service.action("FIGHT Pound")

    assert result == {
        "ok": False,
        "error": "Bulbasaur has no PP remaining for 'Pound'",
    }
    assert emulator.calls == []


def test_switch_accepts_healthy_party_member(monkeypatch, live_battle_service) -> None:
    service, emulator = live_battle_service
    action_calls = []

    def scripted_do_action(current_emulator, party, session, action_type, action_arg):
        action_calls.append((current_emulator, party, session, action_type, action_arg))
        state = read_battle_state(current_emulator.mem, party)
        step_log = StepLog(
            step=1,
            action="SWITCH Incineroar",
            opponent_move=0,
            hp_snapshot=tuple((p.current_hp, p.max_hp) for p in party.members),
            messages=[MessageEvent("Come back, Bulbasaur!", {}, None, "")],
        )
        return session, state, step_log

    monkeypatch.setattr(service_module, "do_action", scripted_do_action)

    result = service.action("SWITCH Incineroar")

    assert len(action_calls) == 1
    assert action_calls[0][0] is emulator
    assert action_calls[0][3:] == ("SWITCH", "Incineroar")
    assert result["ok"] is True
    assert result["messages"] == ["Come back, Bulbasaur!"]
    assert result["observation"]["phase"] == "in_battle"
    assert result["ended"] is False
    assert result["won"] is False


@pytest.mark.parametrize(
    ("action_type", "needs_replacement"),
    [("SWITCH", False), ("SEND", True)],
)
def test_switch_and_send_target_the_requested_rotom_form(
    monkeypatch,
    live_battle_service,
    action_type,
    needs_replacement,
) -> None:
    service, emulator = live_battle_service
    emulator.mem.load_u16(PARTY_BASE_ADDR + 0x20, 714)
    emulator.mem.load_u16(PARTY_BASE_ADDR + SLOT_SIZE + 0x20, 715)
    emulator.mem.load_u16(BATTLE_MONS_BASE + MON_SPECIES, 714)
    emulator.mem.load_u16(BATTLE_MONS_BASE + MON_CUR_HP, 0 if needs_replacement else 100)
    service.session = BattleSession(emu=emulator, party=Party(emulator.mem))
    action_calls = []

    def scripted_do_action(current_emulator, party, session, actual_action_type, action_arg):
        action_calls.append((actual_action_type, action_arg))
        state = read_battle_state(current_emulator.mem, party)
        step_log = StepLog(
            step=1,
            action=f"{actual_action_type} {action_arg}",
            opponent_move=0,
            hp_snapshot=tuple((p.current_hp, p.max_hp) for p in party.members),
            messages=[],
        )
        return session, state, step_log

    monkeypatch.setattr(service_module, "do_action", scripted_do_action)

    result = service.action(f"{action_type} Rotom-frost")

    assert [pokemon.label for pokemon in service.session.party.members] == [
        "Rotom-wash",
        "Rotom-frost",
    ]
    assert action_calls == [(action_type, "Rotom-frost")]
    assert result["ok"] is True

    ambiguous_result = service.action(f"{action_type} Rotom")

    assert ambiguous_result == {
        "ok": False,
        "error": (
            "'Rotom' is not in your party. Available Pokemon: Rotom-wash, "
            "Rotom-frost. Choose one of these, or change your team."
        ),
    }


def test_switch_rejects_fainted_target(live_battle_service, party_memory) -> None:
    service, emulator = live_battle_service
    party_memory.load_u16(PARTY_BASE_ADDR + SLOT_SIZE + 0x56, 0)

    result = service.action("SWITCH Incineroar")

    assert result == {
        "ok": False,
        "error": "'Incineroar' has fainted and can't be sent out. Available Pokemon: Bulbasaur.",
    }
    assert emulator.calls == []


def test_switch_rejects_active_pokemon(live_battle_service) -> None:
    service, emulator = live_battle_service

    result = service.action("SWITCH Bulbasaur")

    assert result == {
        "ok": False,
        "error": "cannot switch to the active Pokemon",
    }
    assert emulator.calls == []


def test_switch_rejects_pokemon_not_in_party(live_battle_service) -> None:
    service, emulator = live_battle_service

    result = service.action("SWITCH Pikachu")

    assert result == {
        "ok": False,
        "error": "'Pikachu' is not in your party. Available Pokemon: Bulbasaur, Incineroar. Choose one of these, or change your team.",
    }
    assert emulator.calls == []


def test_send_accepts_healthy_party_member_when_replacement_is_required(
    monkeypatch,
    live_battle_service,
) -> None:
    service, emulator = live_battle_service
    emulator.mem.load_u16(BATTLE_MONS_BASE + MON_CUR_HP, 0)
    action_calls = []

    def scripted_do_action(current_emulator, party, session, action_type, action_arg):
        action_calls.append((current_emulator, party, session, action_type, action_arg))
        state = read_battle_state(current_emulator.mem, party)
        step_log = StepLog(
            step=1,
            action="SEND Incineroar",
            opponent_move=0,
            hp_snapshot=tuple((p.current_hp, p.max_hp) for p in party.members),
            messages=[MessageEvent("Incineroar, come on back!", {}, None, "")],
        )
        return session, state, step_log

    monkeypatch.setattr(service_module, "do_action", scripted_do_action)

    result = service.action("SEND Incineroar")

    assert len(action_calls) == 1
    assert action_calls[0][0] is emulator
    assert action_calls[0][3:] == ("SEND", "Incineroar")
    assert result["ok"] is True
    assert result["messages"] == ["Incineroar, come on back!"]
    assert result["observation"]["phase"] == "in_battle"
    assert result["ended"] is False
    assert result["won"] is False


def test_send_rejects_fainted_target(live_battle_service, party_memory) -> None:
    service, emulator = live_battle_service
    emulator.mem.load_u16(BATTLE_MONS_BASE + MON_CUR_HP, 0)
    party_memory.load_u16(PARTY_BASE_ADDR + SLOT_SIZE + 0x56, 0)

    result = service.action("SEND Incineroar")

    assert result == {
        "ok": False,
        "error": "'Incineroar' has fainted and can't be sent out. Available Pokemon: Bulbasaur.",
    }
    assert emulator.calls == []


def test_send_rejects_pokemon_not_in_party(live_battle_service) -> None:
    service, emulator = live_battle_service
    emulator.mem.load_u16(BATTLE_MONS_BASE + MON_CUR_HP, 0)

    result = service.action("SEND Pikachu")

    assert result == {
        "ok": False,
        "error": "'Pikachu' is not in your party. Available Pokemon: Bulbasaur, Incineroar. Choose one of these, or change your team.",
    }
    assert emulator.calls == []


def test_send_rejects_live_battle_without_fainted_active_pokemon(live_battle_service) -> None:
    service, emulator = live_battle_service

    result = service.action("SEND Incineroar")

    assert result == {
        "ok": False,
        "error": "SEND is only valid when the active Pokemon has fainted",
    }
    assert emulator.calls == []
