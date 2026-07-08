"""Per-ROM constants for Radical Red: EWRAM addresses, struct offsets, and the
frame budgets the capture loop runs on. All verified empirically against the ROM;
see the inline notes and scripts/ for the derivations.

State-reading (state.py) and message-capture (capture.py) both read raw memory,
so both import from here rather than from each other.
"""

_EWRAM_BASE = 0x02000000

# --- Battle lifecycle / field state -----------------------------------------

# u32: non-zero while in a trainer battle; clears when the battle ends.
BATTLE_TYPE_FLAGS = 0x02022B4C
# Note: _BATTLE_OUTCOME at 0x02022B70 (assumed vanilla+shift) always reads 0.
# Battle end is detected via BATTLE_TYPE_FLAGS -> 0, and win/loss by reading party HP then.

# u16[4]: chosen/last-used move ID per battler slot (battler 1 = opponent).
LAST_MOVES = 0x02023D90

# Weather — confirmed constant across all snap0-snap3 in scan_hazards.py.
BATTLE_WEATHER = 0x02022B50  # u32 bitmask: 0x08 = WEATHER_SANDSTORM_PERMANENT (Sand Stream)
WEATHER_TIMER  = 0x02022883  # u8 countdown; decrements each turn (observed 32->31->30)
WEATHER_SANDSTORM_PERMANENT = 0x08

# gBattlerByTurnOrder — u8: which battler (0=player, 1=opponent) acts first this turn.
# Verified: reads 0 after Fake Out (player priority), 1 when Hippowdon is faster.
BATTLER_TURN_ORDER = 0x02023D6D

# Side status — bit 0x10 = SIDE_STATUS_STEALTH_ROCK; set when SR is placed on that side.
# 0x02023DDE flips 0->16 when Hippowdon uses Stealth Rock (persistent across turns).
# 0x02023DEE is 16 bytes away and likely the opponent-side mirror.
SIDE_STATUS_PLAYER = 0x02023DDE  # u8/u32 bitmask, player's field side
SIDE_STATUS_OPP    = 0x02023DEE  # u8/u32 bitmask, opponent's field side
SIDE_STATUS_STEALTH_ROCK = 0x10

# --- gBattleMons — active battler structs (0x58 bytes each, 4 slots) ---------
# Slot 0 = player's active Pokemon; slot 1 = opponent's active Pokemon.
# Confirmed by matching species u16 at base: 0x03B0=944=Incineroar (slot 0),
# 0x02F7=759=Hippowdon (slot 1).
BATTLE_MONS_BASE = 0x02023BE4  # gBattleMons[0] base address (player active)
BATTLE_MON_SIZE  = 0x58        # bytes per battler struct
OPP_MON_BASE     = BATTLE_MONS_BASE + BATTLE_MON_SIZE  # gBattleMons[1] (opponent active)

# Offsets within a gBattleMons entry:
MON_SPECIES     = 0x00  # u16
MON_ABILITY     = 0x20  # u8 (Intimidate=22, Sand Stream=45)
MON_STAT_STAGES = 0x19  # u8[7]: ATK DEF SPE SPA SPD ACC EVA; neutral=6, range 0-12
MON_CUR_HP      = 0x28  # u16 — decreases with damage
MON_MAX_HP      = 0x2C  # u16 — constant across turns (was 0x2A, which read garbage)

# --- Battle-text buffer ------------------------------------------------------
# gDisplayedStringBattle — the buffer the engine expands each battle message into
# before printing it (post-substitution: nicknames/species already inlined).
# Address confirmed empirically by scripts/find_msg_buffer.py.
MSG_BUFFER    = 0x0202298C
MENU_SENTINEL = "What will"     # "What will <name> do?" — control returned to the player

# --- Frame budgets -----------------------------------------------------------
INTRO_A_PRESSES     = 30   # A presses after battle flag to advance trainer/send-out dialogue
INTRO_SETTLE_FRAMES = 500  # additional wait for auto-advancing messages (Intimidate, weather)
TURN_WAIT_B_PRESSES = 30   # B presses per turn: advances text boxes; safe on battle menu
