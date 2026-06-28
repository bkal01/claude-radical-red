from dataclasses import dataclass

from emulator import Emulator, KEY_A, KEY_B, KEY_DOWN, KEY_LEFT, KEY_RIGHT, KEY_UP
import party

# EWRAM addresses — verified empirically against the Radical Red ROM.
BATTLE_TYPE_FLAGS = 0x02022B4C  # u32: non-zero while in a trainer battle; clears when battle ends
LAST_MOVES        = 0x02023D90  # u16[4]: chosen/last-used move ID per battler slot (battler 1 = opponent)
# Note: _BATTLE_OUTCOME at 0x02022B70 (assumed vanilla+shift) always reads 0.
# Battle end is detected via BATTLE_TYPE_FLAGS → 0, and win/loss by reading party HP at that moment.

# Weather — confirmed by watching 0x08 stay constant through all snap0–snap3 in scan_hazards.py.
BATTLE_WEATHER    = 0x02022B50  # u32 bitmask: 0x08 = sandstorm (WEATHER_SANDSTORM_PERMANENT)
WEATHER_TIMER     = 0x02022883  # u8 countdown; decrements each turn (observed 32→31→30)

# gBattleMons — active battler structs (0x58 bytes each, 4 slots).
# Slot 0 = player's active Pokemon; slot 1 = opponent's active Pokemon.
# Confirmed by matching species u16 at base: 0x03B0=944=Incineroar (slot 0), 0x02F7=759=Hippowdon (slot 1).
BATTLE_MONS_BASE  = 0x02023BE4  # gBattleMons[0] base address (player active)
BATTLE_MON_SIZE   = 0x58        # bytes per battler struct

# Offsets within a gBattleMons entry:
_MON_SPECIES     = 0x00  # u16
_MON_ABILITY     = 0x20  # u8 (Intimidate=22, Sand Stream=45)
_MON_STAT_STAGES = 0x19  # u8[7]: ATK DEF SPE SPA SPD ACC EVA; neutral=6, range 0–12
_MON_CUR_HP      = 0x28  # u16 — verified: decreases with damage
_MON_MAX_HP      = 0x2C  # u16 — verified: constant across turns (was 0x2A, which read garbage)

# gBattlerByTurnOrder — u8: which battler (0=player, 1=opponent) acts first this turn.
# Verified empirically: reads 0 after Fake Out (player priority), 1 when Hippowdon is faster.
BATTLER_TURN_ORDER    = 0x02023D6D

# Side status — bit 0x10 = SIDE_STATUS_STEALTH_ROCK; set when SR is placed on that side.
# 0x02023DDE confirmed to flip 0→16 when Hippowdon uses Stealth Rock (persistent across turns).
# 0x02023DEE is 16 bytes away and likely the opponent-side mirror — verify with Rapid Spin.
SIDE_STATUS_PLAYER = 0x02023DDE  # u8/u32 bitmask, player's field side
SIDE_STATUS_OPP    = 0x02023DEE  # u8/u32 bitmask, opponent's field side

# Frame budgets
INTRO_A_PRESSES     = 30   # A presses after battle flag to advance trainer/send-out dialogue
INTRO_SETTLE_FRAMES = 500  # additional wait for auto-advancing messages (Intimidate, weather)
TURN_WAIT_B_PRESSES = 30   # B presses per turn: advances text boxes; safe on battle menu (cursor stays at FIGHT)

@dataclass
class SideHazards:
    stealth_rock: bool
    spikes: int       # 0–3 layers (address TBD)
    toxic_spikes: int # 0–2 layers (address TBD)

@dataclass
class BattleState:
    party: list[party.PartyPokemon]   # all party members in party-slot order
    active_slot: int                   # which party slot is currently on the field
    needs_replacement: bool            # True when active Pokemon fainted; agent must name a replacement
    weather: int                       # BATTLE_WEATHER bitmask (0x08 = permanent sandstorm)
    weather_turns_left: int | None     # None when weather is permanent (ability-induced); WEATHER_TIMER countdown otherwise
    stat_stages: tuple[int, ...]       # player active: (ATK,DEF,SPE,SPA,SPD,ACC,EVA) neutral=6
    opp_stat_stages: tuple[int, ...]   # opponent active: same layout
    hazards_player: SideHazards        # entry hazards on the player's side
    hazards_opp: SideHazards           # entry hazards on the opponent's side
    opp_species: str                   # Giovanni's current active Pokemon name (or "species_XXX" if unknown)
    opp_ability: str                   # Giovanni's active Pokemon ability name
    opp_current_hp: int | None         # Giovanni's active Pokemon current HP (None if offset unverified)
    opp_max_hp: int | None             # Giovanni's active Pokemon max HP (None if offset unverified)


def read_battle_state(mem, active_slot: int, poke_party: list[party.PartyPokemon]) -> BattleState:
    opp_base    = BATTLE_MONS_BASE + BATTLE_MON_SIZE
    weather_val = mem.u32[BATTLE_WEATHER] & 0xFF
    # bit 0x08 = WEATHER_SANDSTORM_PERMANENT (Sand Stream); timer is irrelevant for permanent weather
    weather_turns_left = None if (weather_val & 0x08) else mem.u8[WEATHER_TIMER]
    stat_stages     = tuple(mem.u8[BATTLE_MONS_BASE + _MON_STAT_STAGES + i] for i in range(7))
    opp_stat_stages = tuple(mem.u8[opp_base + _MON_STAT_STAGES + i] for i in range(7))
    opp_cur = mem.u16[opp_base + _MON_CUR_HP]
    opp_max = mem.u16[opp_base + _MON_MAX_HP]
    opp_species_id = mem.u16[opp_base + _MON_SPECIES]
    return BattleState(
        party=poke_party,
        active_slot=active_slot,
        needs_replacement=mem.u16[BATTLE_MONS_BASE + _MON_CUR_HP] == 0,
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
        opp_species=party.SPECIES_NAME.get(opp_species_id, f"species_{opp_species_id}"),
        opp_ability=party.ABILITY_NAME.get(mem.u8[opp_base + _MON_ABILITY], ""),
        opp_current_hp=opp_cur if opp_cur < 2000 else None,
        opp_max_hp=opp_max if opp_max < 2000 else None,
    )


@dataclass
class StepLog:
    step: int
    action: str                        # e.g. "FIGHT Ice Fang", "SWITCH Gyarados", "SEND Mawile"
    opponent_move: int                 # last move ID used by battler 1; 0 if undetected
    hp_snapshot: tuple                 # ((current_hp, max_hp), ...) per party slot after this step
    opp_species: str = ""              # Giovanni's active Pokemon at the start of this step
    opp_ability: str = ""              # Giovanni's active Pokemon ability at the start of this step
    player_moved_first: bool | None = None  # None for SEND (forced replacement, not a normal turn)

@dataclass
class BattleResult:
    won: bool
    turns: int
    pokemon_remaining: int
    steps: list[StepLog]

@dataclass
class AttemptRecord:
    attempt_num: int
    won: bool
    turns: int
    pokemon_remaining: int
    party_names: list[str]
    steps: list[StepLog]

# ---------------------------------------------------------------------------
# Action executors
# ---------------------------------------------------------------------------

def fight(emu: Emulator, move_name: str, active_party: party.Party, active_slot: int) -> None:
    move_slot = active_party.members[active_slot].moves.index(move_name)
    row, col  = divmod(move_slot, 2)   # 2-column move grid: slot 0→(0,0), 1→(0,1), 2→(1,0), 3→(1,1)

    emu.press(KEY_A)      # open Fight submenu
    emu.step(20)          # wait for submenu to fully open
    # cursor persists from prior turn; reset to top-left before navigating
    emu.press(KEY_UP)
    emu.step(8)
    emu.press(KEY_LEFT)
    emu.step(8)
    for _ in range(row):
        emu.press(KEY_DOWN)
        emu.step(8)
    for _ in range(col):
        emu.press(KEY_RIGHT)
        emu.step(8)
    emu.press(KEY_A)      # confirm move


def _nav_party_slot(emu: Emulator, target: int) -> None:
    # Party screen is a 2x3 grid, slot n is at row=n//2, col=n%2
    # Party screen is a 2×3 grid: slot n is at row=n//2, col=n%2.
    # The cursor persists between party screen openings, so reset to slot 0 first.
    # Assumes no wrap at edges (UP at row 0 stays, LEFT at col 0 stays).
    # for _ in range(3):
    #     emu.press(KEY_UP)
    #     emu.step(8)
    # for _ in range(2):
    #     emu.press(KEY_LEFT)
    #     emu.step(8)
    row, col = divmod(target, 2)
    for _ in range(row):
        emu.press(KEY_DOWN)
        emu.step(8)
    for _ in range(col):
        emu.press(KEY_RIGHT)
        emu.step(8)


def switch(emu: Emulator, pokemon_name: str, active_party: party.Party) -> None:
    """
    Switch pokemon_name in for the active pokemon.
    """
    # Use the visual display slot, not the EWRAM slot. After a forced replacement
    # Radical Red caches a display order that diverges from EWRAM (see send() below).
    target = active_party.get_display_slot(pokemon_name)
    emu.press(KEY_DOWN)   # FIGHT → POKÉMON in the 2×2 battle menu
    emu.step(15)
    emu.press(KEY_A)      # open party screen
    emu.step(80)          # wait for party screen transition to complete (~60 frames)
    _nav_party_slot(emu, target)
    emu.press(KEY_A)      # select Pokemon → SHIFT/CANCEL submenu
    emu.step(20)
    emu.press(KEY_A)      # confirm SHIFT
    emu.step(60)          # allow party screen to close before caller's B-press loop starts


def send(emu: Emulator, pokemon_name: str, active_party: party.Party) -> None:
    """
    Forced replacement — party screen is already open after a faint.
    The faint animation may still be playing; wait for the party screen to appear first.

    Radical Red reorders EWRAM when the active Pokemon faints (fainted mons go to the
    front), and the party screen shows that reordered layout. After the player selects a
    replacement at display slot S, the game caches a new display order with the sent-in
    Pokemon at slot 0 (swap of slots 0 and S) — but EWRAM is then restored to its
    pre-faint order. Future voluntary-switch party screens use the cached display order,
    not the current EWRAM order, so we must track it explicitly.
    """
    # At this point active_party.members already reflects the faint-reordered EWRAM
    # (captured by the top-of-loop refresh()). Sync display_pos to that same order so
    # the visual slot == EWRAM slot, which is true at forced-replacement time.
    active_party._sync_display_to_ewram()
    target = active_party.get_display_slot(pokemon_name)
    emu.step(80)          # wait for party screen transition to complete
    _nav_party_slot(emu, target)
    emu.press(KEY_A)      # select → SEND OUT submenu
    emu.step(20)
    emu.press(KEY_A)      # confirm SEND OUT
    emu.step(60)
    # Game swaps display order: sent-in Pokemon → slot 0, old slot-0 → sent-in's old slot.
    active_party._update_display_after_send(pokemon_name)


def execute(emu: Emulator, kind: str, arg: str, active_party: party.Party, active_slot: int) -> None:
    if kind == "FIGHT":
        fight(emu, arg, active_party, active_slot)
    elif kind == "SWITCH":
        switch(emu, arg, active_party)
    elif kind == "SEND":
        send(emu, arg, active_party)
    else:
        raise ValueError(f"Unknown action kind: {kind!r}")


def _b_press_loop(emu: Emulator) -> tuple[bool, bool]:
    """Press B to advance text; poll for battle end each press. Returns (ended, won)."""
    for _ in range(TURN_WAIT_B_PRESSES):
        emu.press(KEY_B, hold_frames=1)
        emu.step(60)
        if emu.mem.u32[BATTLE_TYPE_FLAGS] == 0:
            return True, emu.mem.u16[BATTLE_MONS_BASE + _MON_CUR_HP] > 0
    return False, False


def _find_active_slot(mem, active_party: party.Party) -> int:
    """Re-derive active_slot from gBattleMons[0] species after any turn.

    Reading gBattleMons[0] directly is immune to EWRAM party reordering that
    Radical Red performs when the active Pokemon faints (forced replacement).
    """
    species_id = mem.u16[BATTLE_MONS_BASE + _MON_SPECIES]
    name = party.SPECIES_NAME.get(species_id, f"species_{species_id}")
    try:
        return active_party.get_slot_number(name)
    except KeyError:
        return 0


def run(emu: Emulator, agent, active_party: party.Party) -> BattleResult:
    """
    Execute one full Giovanni battle attempt.

    agent.step is called each turn with the current BattleState and the
    full step history so far. It returns one action string:
      FIGHT <move_name>  — voluntary move from the battle menu
      SWITCH <pokemon>   — voluntary switch from the battle menu
      SEND <pokemon>     — forced replacement after a faint

    Battle end is detected by polling BATTLE_TYPE_FLAGS every 5 frames inside
    the post-action B-press loop. When the flags clear, party HP is read immediately
    (before EWRAM is overwritten) to determine win/loss.
    """
    # Walk into the room to trigger Giovanni's encounter script.
    for _ in range(60):
        emu._core.set_keys(KEY_UP)
        emu._core.run_frame()
        emu._core.set_keys()

    # Advance through Giovanni's dialogue until the battle flag is set.
    # Hold A for 3 frames (registers the press + speeds up text scroll),
    # then release for 20 frames so the game can process the edge.
    for _ in range(120):
        if emu.mem.u32[BATTLE_TYPE_FLAGS] != 0:
            break
        emu.press(KEY_A, hold_frames=3)
        emu.step(20)
    else:
        raise RuntimeError("Battle did not start — check the save state position")

    # Advance trainer intro and send-out dialogue with A, then let auto-advance
    # messages (Intimidate, weather abilities) finish on their own.
    for _ in range(INTRO_A_PRESSES):
        emu.press(KEY_A, hold_frames=3)
        emu.step(40)
    emu.step(INTRO_SETTLE_FRAMES)

    active_slot = 0  # lead is always party slot 0; updated after each switch
    steps = []
    step  = 0

    """
    In a loop, we will:
    1. Get the current state of the battle
    2. Get the next action from the agent via step()
    3. Execute that action and skip through any text prompts
    4. Capture a log of what just happened (HP diffs, who moved first, did the battle end, etc.)
    """
    while True:
        active_party.refresh()
        state  = read_battle_state(emu.mem, active_slot, active_party.members)
        emu.pause_recording()
        action_string = agent.step(state, steps)
        emu.resume_recording()

        action_type, action_arg = action_string.split(maxsplit=1)
        execute(emu, action_type, action_arg, active_party, active_slot)
        player_first = None if action_type == "SEND" else (emu.mem.u8[BATTLER_TURN_ORDER] == 0)
        ended, won = _b_press_loop(emu)

        opp_move = emu.mem.u16[LAST_MOVES + 2]
        active_party.refresh()
        hp_snap = tuple((p.current_hp, p.max_hp) for p in active_party.members)
        if not ended:
            active_slot = _find_active_slot(emu.mem, active_party)

        step += 1
        steps.append(StepLog(
            step=step,
            action=action_string,
            opponent_move=opp_move,
            hp_snapshot=hp_snap,
            opp_species=state.opp_species,
            opp_ability=state.opp_ability,
            player_moved_first=player_first,
        ))

        if ended:
            break

    pokemon_remaining = sum(1 for hp, _ in steps[-1].hp_snapshot if hp > 0)
    return BattleResult(
        won=won,
        turns=len(steps),
        pokemon_remaining=pokemon_remaining,
        steps=steps,
    )
