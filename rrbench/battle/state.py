from dataclasses import dataclass, field

from rrbench.battle.addresses import (
    BATTLE_MONS_BASE, BATTLE_MON_SIZE, BATTLE_TERRAIN, BATTLE_TYPE_FLAGS, BATTLE_WEATHER,
    MON_ABILITY, MON_CUR_HP, MON_MAX_HP, MON_SPECIES, MON_STAT_STAGES,
    SIDE_HAZARDS_OPP, SIDE_HAZARDS_PLAYER,
    SIDE_HAZARDS_SPIKES_MASK, SIDE_HAZARDS_STEALTH_ROCK,
    SIDE_HAZARDS_STICKY_WEB, SIDE_HAZARDS_TOXIC_SPIKES_MASK,
    TERRAIN_TIMER, WEATHER_TIMER,
    WEATHER_RAIN, WEATHER_SANDSTORM, WEATHER_SNOW, WEATHER_SUN,
)
from rrbench.battle.capture import MessageEvent
from rrbench.battle.control import BattleControlState, read_battle_control_state
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
    num_steps: int = 0
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
    spikes: int
    toxic_spikes: int
    sticky_web: bool

@dataclass
class BattleState:
    party: Party                       # full Party, `members` is in party-slot order
    active_slot: int                   # which party slot is currently on the field
    control_state: BattleControlState  # action selection, replacement selection, or transition
    weather: int                       # raw BATTLE_WEATHER bitmask
    weather_kind: str                  # protocol weather kind decoded from the raw flags
    weather_turns_left: int | None     # None for active permanent weather; 0 for no weather
    terrain: int                       # BATTLE_TERRAIN enum: none, Electric, Grassy, Misty, Psychic
    terrain_turns_left: int            # TERRAIN_TIMER countdown; 0 when there is no terrain
    stat_stages: tuple[int, ...]       # player active: (ATK,DEF,SPE,SPA,SPD,ACC,EVA) neutral=6
    opp_stat_stages: tuple[int, ...]   # opponent active: same layout
    hazards_player: SideHazards        # entry hazards on the player's side
    hazards_opp: SideHazards           # entry hazards on the opponent's side
    opp_species: str                   # Giovanni's current active Pokemon name (or "species_XXX" if unknown)
    opp_species_id: int                # Giovanni's active Pokemon species ID (disambiguates base/mega/regional forms)
    opp_ability: str                   # Giovanni's active Pokemon ability name
    opp_current_hp: int | None         # Giovanni's active Pokemon current HP (None if offset unverified)
    opp_max_hp: int | None             # Giovanni's active Pokemon max HP (None if offset unverified)

    @property
    def needs_replacement(self) -> bool:
        """Whether the game is currently waiting for a forced replacement."""
        return self.control_state is BattleControlState.REPLACEMENT_SELECT


WEATHER_FLAGS = (
    ("rain", WEATHER_RAIN),
    ("sandstorm", WEATHER_SANDSTORM),
    ("sun", WEATHER_SUN),
    ("snow", WEATHER_SNOW),
)


def decode_weather(weather: int, timer: int) -> tuple[str, int | None]:
    """Decode verified RR v4.1 battle weather state.

    A nonzero timer is the remaining temporary-weather duration. Permanent map
    weather has an active kind bit with a zero timer (Route 25 rain is 0x05/0).
    """
    for kind, flag in WEATHER_FLAGS:
        if weather & flag:
            return kind, None if timer == 0 else timer
    return "none", 0


def in_battle(mem) -> bool:
    """True while a trainer battle is live. BATTLE_TYPE_FLAGS is non-zero during the
    battle and clears to 0 when it ends."""
    return mem.u32[BATTLE_TYPE_FLAGS] != 0


def read_battle_state(mem, party: Party) -> BattleState:
    opp_base    = BATTLE_MONS_BASE + BATTLE_MON_SIZE
    weather_val = mem.u32[BATTLE_WEATHER]
    weather_kind, weather_turns_left = decode_weather(
        weather_val, mem.u32[WEATHER_TIMER]
    )
    terrain = mem.u8[BATTLE_TERRAIN]
    terrain_turns_left = mem.u8[TERRAIN_TIMER]
    stat_stages     = tuple(mem.u8[BATTLE_MONS_BASE + MON_STAT_STAGES + i] for i in range(7))
    opp_stat_stages = tuple(mem.u8[opp_base + MON_STAT_STAGES + i] for i in range(7))
    opp_cur = mem.u16[opp_base + MON_CUR_HP]
    opp_max = mem.u16[opp_base + MON_MAX_HP]
    opp_species_id = mem.u16[opp_base + MON_SPECIES]
    hazards_player = mem.u8[SIDE_HAZARDS_PLAYER]
    hazards_opp = mem.u8[SIDE_HAZARDS_OPP]

    species_id = mem.u16[BATTLE_MONS_BASE + MON_SPECIES]
    active_slot = party.get_slot_number(species_id)

    return BattleState(
        party=party,
        active_slot=active_slot,
        control_state=read_battle_control_state(mem),
        weather=weather_val,
        weather_kind=weather_kind,
        weather_turns_left=weather_turns_left,
        terrain=terrain,
        terrain_turns_left=terrain_turns_left,
        stat_stages=stat_stages,
        opp_stat_stages=opp_stat_stages,
        hazards_player=SideHazards(
            stealth_rock=bool(hazards_player & SIDE_HAZARDS_STEALTH_ROCK),
            spikes=hazards_player & SIDE_HAZARDS_SPIKES_MASK,
            toxic_spikes=(hazards_player & SIDE_HAZARDS_TOXIC_SPIKES_MASK) >> 2,
            sticky_web=bool(hazards_player & SIDE_HAZARDS_STICKY_WEB),
        ),
        hazards_opp=SideHazards(
            stealth_rock=bool(hazards_opp & SIDE_HAZARDS_STEALTH_ROCK),
            spikes=hazards_opp & SIDE_HAZARDS_SPIKES_MASK,
            toxic_spikes=(hazards_opp & SIDE_HAZARDS_TOXIC_SPIKES_MASK) >> 2,
            sticky_web=bool(hazards_opp & SIDE_HAZARDS_STICKY_WEB),
        ),
        opp_species=SPECIES_NAME.get(opp_species_id, f"species_{opp_species_id}"),
        opp_species_id=opp_species_id,
        opp_ability=ABILITY_NAME.get(mem.u8[opp_base + MON_ABILITY], ""),
        opp_current_hp=opp_cur if opp_cur < 2000 else None,
        opp_max_hp=opp_max if opp_max < 2000 else None,
    )
