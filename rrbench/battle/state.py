from dataclasses import dataclass, field

from rrbench.battle.addresses import (
    BATTLE_MONS_BASE, BATTLE_MON_SIZE, BATTLE_WEATHER,
    MON_ABILITY, MON_CUR_HP, MON_MAX_HP, MON_SPECIES, MON_STAT_STAGES,
    SIDE_STATUS_PLAYER, SIDE_STATUS_OPP,
    WEATHER_TIMER,
)
from rrbench.battle.capture import MessageEvent
from rrbench.emulator.emulator import Emulator
from rrbench.emulator.memory import (
    ABILITY_NAME, SPECIES_NAME,
    Party, PartyPokemon,
)


@dataclass
class BattleSession:
    """Live handle to an in-progress battle. Created by start_battle() and threaded
    through do_action(); the trajectory/log is owned by the harness, not stored here."""
    emu: Emulator
    party: Party
    active_slot: int = 0
    ended: bool = False
    won: bool = False

@dataclass
class StepLog:
    step: int
    action: str                        # e.g. "FIGHT Ice Fang", "SWITCH Gyarados", "SEND Mawile"
    opponent_move: int                 # last move ID used by battler 1; 0 if undetected
    hp_snapshot: tuple                 # ((current_hp, max_hp), ...) per party slot after this step
    opp_species: str = ""              # Giovanni's active Pokemon at the start of this step
    opp_species_id: int = 0            # species ID for the above (disambiguates base/mega/regional forms)
    opp_ability: str = ""              # Giovanni's active Pokemon ability at the start of this step
    messages: list[MessageEvent] = field(default_factory=list)  # verbatim text captured during this step

@dataclass
class SideHazards:
    stealth_rock: bool
    spikes: int       # 0–3 layers (address TBD)
    toxic_spikes: int # 0–2 layers (address TBD)

@dataclass
class BattleState:
    party: list[PartyPokemon]   # all party members in party-slot order
    active_slot: int                   # which party slot is currently on the field
    needs_replacement: bool            # True when active Pokemon fainted; agent must name a replacement
    weather: int                       # BATTLE_WEATHER bitmask (0x08 = permanent sandstorm)
    weather_turns_left: int | None     # None when weather is permanent (ability-induced); WEATHER_TIMER countdown otherwise
    stat_stages: tuple[int, ...]       # player active: (ATK,DEF,SPE,SPA,SPD,ACC,EVA) neutral=6
    opp_stat_stages: tuple[int, ...]   # opponent active: same layout
    hazards_player: SideHazards        # entry hazards on the player's side
    hazards_opp: SideHazards           # entry hazards on the opponent's side
    opp_species: str                   # Giovanni's current active Pokemon name (or "species_XXX" if unknown)
    opp_species_id: int                # Giovanni's active Pokemon species ID (disambiguates base/mega/regional forms)
    opp_ability: str                   # Giovanni's active Pokemon ability name
    opp_current_hp: int | None         # Giovanni's active Pokemon current HP (None if offset unverified)
    opp_max_hp: int | None             # Giovanni's active Pokemon max HP (None if offset unverified)


def read_battle_state(mem, active_slot: int, poke_party: list[PartyPokemon]) -> BattleState:
    opp_base    = BATTLE_MONS_BASE + BATTLE_MON_SIZE
    weather_val = mem.u32[BATTLE_WEATHER] & 0xFF
    # bit 0x08 = WEATHER_SANDSTORM_PERMANENT (Sand Stream); timer is irrelevant for permanent weather
    # TODO: support other kinds of (permanent) weather
    weather_turns_left = None if (weather_val & 0x08) else mem.u8[WEATHER_TIMER]
    stat_stages     = tuple(mem.u8[BATTLE_MONS_BASE + MON_STAT_STAGES + i] for i in range(7))
    opp_stat_stages = tuple(mem.u8[opp_base + MON_STAT_STAGES + i] for i in range(7))
    opp_cur = mem.u16[opp_base + MON_CUR_HP]
    opp_max = mem.u16[opp_base + MON_MAX_HP]
    opp_species_id = mem.u16[opp_base + MON_SPECIES]
    return BattleState(
        party=poke_party,
        active_slot=active_slot,
        needs_replacement=mem.u16[BATTLE_MONS_BASE + MON_CUR_HP] == 0,
        weather=weather_val,
        weather_turns_left=weather_turns_left,
        stat_stages=stat_stages,
        opp_stat_stages=opp_stat_stages,
        hazards_player=SideHazards(
            stealth_rock=bool(mem.u8[SIDE_STATUS_PLAYER] & 0x10),
            spikes=0,
            toxic_spikes=0,
        ),
        hazards_opp=SideHazards(
            stealth_rock=bool(mem.u8[SIDE_STATUS_OPP] & 0x10),
            spikes=0,
            toxic_spikes=0,
        ),
        opp_species=SPECIES_NAME.get(opp_species_id, f"species_{opp_species_id}"),
        opp_species_id=opp_species_id,
        opp_ability=ABILITY_NAME.get(mem.u8[opp_base + MON_ABILITY], ""),
        opp_current_hp=opp_cur if opp_cur < 2000 else None,
        opp_max_hp=opp_max if opp_max < 2000 else None,
    )