from rrbench.battle.capture import MessageEvent
from rrbench.battle.state import BattleState, SideHazards

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
        # PP remaining only — dynamic and the reason to surface it live; max PP is static
        # (agent has it from the roster / moves.json). Empty move slots are dropped.
        "moves": [{"name": m, "pp_remaining": pp} for m, pp in zip(p.moves, p.pp) if m],
    }


def render_pre_battle(party) -> dict:
    """The no-battle observation: legal before `lead` (and after `reset`). Exposes only
    the player's own roster — there is no active battle to read."""
    return {
        "phase": "no_battle",
        "party": [render_pokemon(p, active=False) for p in party.members],
    }


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
