import pytest

from rrbench.interface.service import BattleService
from rrbench.tasks import load_task


@pytest.mark.integration
def test_fight_after_switch_to_corviknight_uses_selected_move() -> None:
    service = BattleService(load_task("tasks/giovanni-silph-co-easy"))
    team = {
        "members": [
            {
                "slot": 0,
                "species_id": 285,
                "level": 57,
                "nature_id": 3,
                "ability_id": 67,
                "move_ids": [330, 89, 58, 157],
                "held_item_id": 0,
                "evs": {"HP": 252, "ATK": 252, "DEF": 4, "SPE": 0, "SPA": 0, "SPDEF": 0},
            },
            {
                "slot": 1,
                "species_id": 130,
                "level": 57,
                "nature_id": 13,
                "ability_id": 22,
                "move_ids": [358, 432, 242, 269],
                "held_item_id": 0,
                "evs": {"HP": 4, "ATK": 252, "DEF": 0, "SPE": 252, "SPA": 0, "SPDEF": 0},
            },
            {
                "slot": 2,
                "species_id": 394,
                "level": 57,
                "nature_id": 10,
                "ability_id": 36,
                "move_ids": [817, 466, 85, 373],
                "held_item_id": 0,
                "evs": {"HP": 4, "ATK": 0, "DEF": 0, "SPE": 252, "SPA": 252, "SPDEF": 0},
            },
            {
                "slot": 3,
                "species_id": 498,
                "level": 57,
                "nature_id": 3,
                "ability_id": 8,
                "move_ids": [337, 89, 429, 424],
                "held_item_id": 0,
                "evs": {"HP": 4, "ATK": 252, "DEF": 0, "SPE": 252, "SPA": 0, "SPDEF": 0},
            },
            {
                "slot": 4,
                "species_id": 1115,
                "level": 57,
                "nature_id": 8,
                "ability_id": 192,
                "move_ids": [361, 382, 395, 442],
                "held_item_id": 0,
                "evs": {"HP": 252, "ATK": 0, "DEF": 252, "SPE": 0, "SPA": 0, "SPDEF": 4},
            },
            {
                "slot": 5,
                "species_id": 248,
                "level": 57,
                "nature_id": 3,
                "ability_id": 45,
                "move_ids": [242, 429, 89, 432],
                "held_item_id": 0,
                "evs": {"HP": 4, "ATK": 252, "DEF": 0, "SPE": 252, "SPA": 0, "SPDEF": 0},
            },
        ]
    }

    assert service.apply_team(team)["ok"] is True
    service.active_team_config.apply(service.emu.mem)
    assert service.lead("Gyarados")["ok"] is True
    assert service.action("FIGHT Aqua Tail")["ok"] is True
    assert service.action("FIGHT Aqua Tail")["ok"] is True
    assert service.action("SWITCH Corviknight")["ok"] is True

    result = service.action("FIGHT U-turn")

    assert "Corviknigh used U-turn!" in result["messages"]
    corviknight = next(
        pokemon
        for pokemon in result["observation"]["party"]
        if pokemon["name"] == "Corviknight"
    )
    assert corviknight["moves"][3]["pp_remaining"] == 19


@pytest.mark.integration
def test_ghost_pokemon_tower_confirmation_faint_can_send_replacement() -> None:
    """A faint in this unescapable wild battle must still reach SEND selection.

    The game asks "Use next Pokémon?" rather than immediately opening the forced
    replacement screen. The current capture loop advances that prompt, after which
    the encounter rejects the attempted escape and allows the agent to SEND its
    healthy bench Pokemon.
    """
    service = BattleService(load_task("tasks/ghost-pokemon-tower"))
    team = {
        "members": [
            {"slot": 0, "species_id": 129, "level": 1},  # Magikarp
            {"slot": 1, "species_id": 10, "level": 1},   # Caterpie
        ]
    }

    assert service.apply_team(team)["ok"] is True
    assert service.active_team_config is not None
    service.active_team_config.apply(service.emu.mem)
    assert service.lead("Magikarp")["ok"] is True

    faint_result = service.action("FIGHT Splash")

    assert faint_result["ok"] is True
    assert faint_result["ended"] is False
    assert faint_result["won"] is False
    assert "Magikarp fainted!" in faint_result["messages"]
    assert "Use next Pokémon?" in faint_result["messages"]
    faint_observation = faint_result["observation"]
    assert faint_observation["needs_replacement"] is True
    assert faint_observation["active"]["name"] == "Magikarp"
    party = {pokemon["name"]: pokemon for pokemon in faint_observation["party"]}
    assert party["Magikarp"]["fainted"] is True
    assert party["Caterpie"]["fainted"] is False

    send_result = service.action("SEND Caterpie")

    assert send_result["ok"] is True
    assert send_result["ended"] is False
    assert send_result["won"] is False
    assert "Go! Caterpie!" in send_result["messages"]
    assert send_result["observation"]["needs_replacement"] is False
    assert send_result["observation"]["active"]["name"] == "Caterpie"
