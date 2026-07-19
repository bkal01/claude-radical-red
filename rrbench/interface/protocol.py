from rrbench.battle.capture import MessageEvent
from rrbench.battle.state import BattleState, SideHazards
from rrbench.emulator.memory import ABILITY_NAME, MOVE_NAME, SPECIES_NAME, SPECIES_TYPES
from rrbench.team import NATURE_NAMES, TeamConfig

STAT_LABELS = ("ATK", "DEF", "SPE", "SPA", "SPD", "ACC", "EVA")


def render_stat_stages(raw: tuple[int, ...]) -> dict[str, int]:
    # RAM stores stages biased by +6 (neutral). Emit signed offsets, all seven
    # keys always present so the schema shape is fixed rather than sparse.
    return {label: raw[i] - 6 for i, label in enumerate(STAT_LABELS)}


def render_hazards(h: SideHazards) -> dict:
    return {
        "stealth_rock": h.stealth_rock,
        "spikes": h.spikes,
        "toxic_spikes": h.toxic_spikes,
    }


def render_weather(state: BattleState) -> dict:
    # Only permanent sandstorm (Sand Stream) is modeled today; see read_battle_state.
    kind = "sandstorm" if (state.weather & 0x08) else "none"
    turns_left = state.weather_turns_left if state.weather_turns_left else "inf"
    return {"kind": kind, "turns_left": turns_left}


def render_pokemon(p, active: bool) -> dict:
    return {
        "name": p.name,
        "current_hp": p.current_hp,
        "max_hp": p.max_hp,
        "status": p.status,
        "active": active,
        "fainted": p.current_hp == 0,
        # PP remaining only — dynamic and the reason to surface it live; max PP is in moves.json.
        "moves": [{"name": m, "pp_remaining": pp} for m, pp in zip(p.moves, p.pp) if m],
    }


def render_pre_battle(party) -> dict:
    """The no-battle observation: legal before `lead` (and after `reset`). Exposes only
    the player's own roster — there is no active battle to read."""
    return {
        "phase": "no_battle",
        "party": [render_pokemon(p, active=False) for p in party.members],
    }


def render_team(config: TeamConfig) -> dict:
    members = []
    for slot, member in enumerate(config.members):
        calculated_stats = member.calculated_stats()
        members.append(
            {
                "slot": slot,
                "species_id": member.species_id,
                "name": SPECIES_NAME.get(member.species_id, f"species_{member.species_id}"),
                "types": SPECIES_TYPES.get(member.species_id, []),
                "level": member.level,
                "nature": {
                    "id": member.nature_id,
                    "name": (
                        NATURE_NAMES[member.nature_id]
                        if member.nature_id is not None
                        else None
                    ),
                },
                "ability_id": member.ability_id,
                "ability": ABILITY_NAME.get(member.ability_id or 0, ""),
                "held_item_id": member.held_item,
                "moves": [
                    {
                        "slot": move_slot,
                        "move_id": move_id,
                        "name": MOVE_NAME.get(move_id, ""),
                    }
                    for move_slot, move_id in enumerate(member.move_ids or ())
                ],
                "evs": dict(member.evs),
                "stats": {
                    "HP": calculated_stats["MAXHP"],
                    "ATK": calculated_stats["ATK"],
                    "DEF": calculated_stats["DEF"],
                    "SPE": calculated_stats["SPE"],
                    "SPA": calculated_stats["SPA"],
                    "SPDEF": calculated_stats["SPDEF"],
                },
            }
        )
    return {"members": members}


def render_observation(state: BattleState) -> dict:
    """
    Render a BattleState into a form that's consumable by an agent via cli.
    """
    members = state.party.members
    return {
        "phase": "in_battle",
        "needs_replacement": state.needs_replacement,
        "active": {
            "name": members[state.active_slot].name,
            "slot": state.active_slot,
        },
        "party": [
            render_pokemon(p, active=(i == state.active_slot)) for i, p in enumerate(members)
        ],
        "opponent": {
            "species": state.opp_species,
            "species_id": state.opp_species_id,
            "ability": state.opp_ability,
            "current_hp": state.opp_current_hp,
            "max_hp": state.opp_max_hp,
        },
        "weather": render_weather(state),
        "hazards": {
            "player": render_hazards(state.hazards_player),
            "opponent": render_hazards(state.hazards_opp),
        },
        "stat_stages": {
            "player": render_stat_stages(state.stat_stages),
            "opponent": render_stat_stages(state.opp_stat_stages),
        },
    }

def render_messages(messages: list[MessageEvent]) -> list[str]:
    """
    Render a list of MessageEvents into a form that's consumable by an agent via cli.
    """
    return [ev.text for ev in messages]
