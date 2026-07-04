import struct

from battle import EpisodeRecord, BattleState, SideHazards, StepLog
from party import MOVE_DATA, MOVE_NAME, party_count, read_slot, PARTY_BASE_ADDR, SLOT_SIZE

_GBA_ROM = 0x08000000

_MOVE_NAME_TABLE  = 0x010EEEDC
_MOVE_NAME_STRIDE = 17
_MOVE_DATA_TABLE  = 0x011521D0
_MOVE_DATA_STRIDE = 12
_MOVE_DESC_PTRS   = 0x0103DF70
_ABILITY_NAME_TABLE  = 0x010E32C0
_ABILITY_NAME_STRIDE = 17
_ABILITY_DESC_PTRS   = 0x01009B84
_ITEM_TABLE  = 0x013C0000
_ITEM_STRIDE = 44
_SPECIES3_TABLE    = 0x00254784
_SPECIES_EXT_TABLE = 0x017B98EC
_SPECIES_STRIDE    = 28
_GEN3_SPECIES      = set(range(1, 387))

_PID   = 0x00
_ATK   = 0x5A
_DEF   = 0x5C
_SPD   = 0x5E
_SPATK = 0x60
_SPDEF = 0x62

_NATURES = [
    "Hardy",   "Lonely",  "Brave",   "Adamant", "Naughty",
    "Bold",    "Docile",  "Relaxed", "Impish",  "Lax",
    "Timid",   "Hasty",   "Serious", "Jolly",   "Naive",
    "Modest",  "Mild",    "Quiet",   "Bashful", "Rash",
    "Calm",    "Gentle",  "Sassy",   "Careful", "Quirky",
]
_NATURE_EFFECT = {
    "Hardy": None,   "Lonely": ("+ATK","-DEF"),   "Brave": ("+ATK","-SPD"),
    "Adamant": ("+ATK","-SPATK"), "Naughty": ("+ATK","-SPDEF"),
    "Bold": ("+DEF","-ATK"),     "Docile": None,  "Relaxed": ("+DEF","-SPD"),
    "Impish": ("+DEF","-SPATK"), "Lax": ("+DEF","-SPDEF"),
    "Timid": ("+SPD","-ATK"),    "Hasty": ("+SPD","-DEF"),  "Serious": None,
    "Jolly": ("+SPD","-SPATK"),  "Naive": ("+SPD","-SPDEF"),
    "Modest": ("+SPATK","-ATK"), "Mild": ("+SPATK","-DEF"), "Quiet": ("+SPATK","-SPD"),
    "Bashful": None,             "Rash": ("+SPATK","-SPDEF"),
    "Calm": ("+SPDEF","-ATK"),   "Gentle": ("+SPDEF","-DEF"), "Sassy": ("+SPDEF","-SPD"),
    "Careful": ("+SPDEF","-SPATK"), "Quirky": None,
}
_TYPES = {
    0: "Normal", 1: "Fighting", 2: "Flying", 3: "Poison", 4: "Ground",
    5: "Rock",   6: "Bug",      7: "Ghost",  8: "Steel",  9: "???",
    10: "Fire",  11: "Water",   12: "Grass", 13: "Electric", 14: "Psychic",
    15: "Ice",   16: "Dragon",  17: "Dark",  18: "Fairy", 23: "Fairy",
}
_CATEGORIES = {0: "Physical", 1: "Special", 2: "Status"}


def _decode(rom: bytes, offset: int, max_len: int = 200) -> str:
    out = []
    for b in rom[offset:offset + max_len]:
        if b == 0xFF:
            break
        if 0xBB <= b <= 0xD4:   out.append(chr(ord('A') + b - 0xBB))
        elif 0xD5 <= b <= 0xEE: out.append(chr(ord('a') + b - 0xD5))
        elif b in (0x00, 0xA0): out.append(' ')
        elif b == 0xAD:         out.append('.')
        elif b == 0xAE:         out.append('-')
        elif 0xA1 <= b <= 0xAA: out.append(str(b - 0xA1))
        elif b == 0xFE:         out.append('\n')
        elif b == 0x5B:         out.append('%')
        elif b == 0xB4:         out.append("'")
        elif b == 0xB8:         out.append(',')
        elif b == 0x1B:         out.append('e')
        elif b == 0xAB:         out.append('!')
        elif b == 0xAC:         out.append('?')
        else: break
    return ''.join(out).strip()


def _gba_ptr(rom: bytes, offset: int) -> int | None:
    v = struct.unpack_from('<I', rom, offset)[0]
    off = v - _GBA_ROM
    return off if 0 < off < len(rom) else None


def _species_ability_id(rom: bytes, species_id: int, ability_index: int) -> int:
    if species_id in _GEN3_SPECIES:
        base = _SPECIES3_TABLE + species_id * _SPECIES_STRIDE
        return rom[base + 23] if ability_index == 1 else rom[base + 22]
    else:
        base = _SPECIES_EXT_TABLE + species_id * _SPECIES_STRIDE
        ab0, ab1, ha = rom[base + 22], rom[base + 23], rom[base + 26]
        return (ab1 if ab1 != 0 else ha) if ability_index == 1 else ab0


def build_team_description(mem, rom: bytes) -> str:
    lines: list[str] = ["# Player Team\n"]

    for slot in range(party_count(mem)):
        poke = read_slot(mem, slot)
        base = PARTY_BASE_ADDR + slot * SLOT_SIZE

        pid    = mem.u32[base + _PID]
        nature = _NATURES[pid % 25]
        effect = _NATURE_EFFECT[nature]
        nature_str = f"{nature} ({effect[0]}, {effect[1]})" if effect else f"{nature} (neutral)"

        ab_id   = _species_ability_id(rom, poke.species_id, pid & 1)
        ab_name = _decode(rom, _ABILITY_NAME_TABLE + ab_id * _ABILITY_NAME_STRIDE, _ABILITY_NAME_STRIDE) if ab_id else '(none)'
        ab_desc_ptr = _gba_ptr(rom, _ABILITY_DESC_PTRS + ab_id * 4)
        ab_desc = ' '.join(_decode(rom, ab_desc_ptr, 200).split()) if ab_desc_ptr else ''

        item_name = _decode(rom, _ITEM_TABLE + poke.held_item * _ITEM_STRIDE, 14) if poke.held_item else 'None'
        item_desc_ptr = _gba_ptr(rom, _ITEM_TABLE + poke.held_item * _ITEM_STRIDE + 20) if poke.held_item else None
        item_desc = ' '.join(_decode(rom, item_desc_ptr, 200).split()) if item_desc_ptr else ''

        a0 = mem.u32[base + 0x2C]
        a1 = mem.u32[base + 0x30]
        a2 = mem.u32[base + 0x34]
        move_ids = (a0 & 0xFFFF, (a0 >> 16) & 0xFFFF, a1 & 0xFFFF, (a1 >> 16) & 0xFFFF)
        move_pps = (a2 & 0xFF, (a2 >> 8) & 0xFF, (a2 >> 16) & 0xFF, (a2 >> 24) & 0xFF)

        lines.append(f"## {poke.name}\n")
        lines.append(
            f"**Level:** {poke.level}  **Nature:** {nature_str}\n"
        )
        lines.append(
            f"**Stats:** HP {poke.max_hp} | ATK {mem.u16[base + _ATK]} | DEF {mem.u16[base + _DEF]} | "
            f"SPATK {mem.u16[base + _SPATK]} | SPDEF {mem.u16[base + _SPDEF]} | SPD {mem.u16[base + _SPD]}\n"
        )
        e0 = mem.u32[base + 0x38]
        e1 = mem.u32[base + 0x3C]
        lines.append(
            f"**EVs:** HP {e0 & 0xFF} | ATK {(e0 >> 8) & 0xFF} | DEF {(e0 >> 16) & 0xFF} | "
            f"SPATK {e1 & 0xFF} | SPDEF {(e1 >> 8) & 0xFF} | SPD {(e0 >> 24) & 0xFF}\n"
        )
        lines.append(f"**Ability:** {ab_name}" + (f" — {ab_desc}" if ab_desc else "") + "\n")
        lines.append(f"**Item:** {item_name}" + (f" — {item_desc}" if item_desc else "") + "\n")
        lines.append("**Moves:**\n")

        for move_id, cur_pp in zip(move_ids, move_pps):
            if move_id == 0:
                continue
            mname_addr = _MOVE_NAME_TABLE + move_id * _MOVE_NAME_STRIDE
            mname = _decode(rom, mname_addr, _MOVE_NAME_STRIDE)
            maddr = _MOVE_DATA_TABLE + move_id * _MOVE_DATA_STRIDE
            mtype     = _TYPES.get(rom[maddr + 2], f'type{rom[maddr + 2]}')
            mcat      = _CATEGORIES.get(rom[maddr + 10], '?')
            power_str = str(rom[maddr + 1]) if rom[maddr + 1] else '—'
            acc_str   = f"{rom[maddr + 3]}%" if rom[maddr + 3] else '—'
            base_pp   = rom[maddr + 4]
            desc_ptr  = _gba_ptr(rom, _MOVE_DESC_PTRS + move_id * 4)
            mdesc     = ' '.join(_decode(rom, desc_ptr, 300).split()) if desc_ptr else ''
            lines.append(
                f"  - **{mname}** | {mtype} | {mcat} | Power: {power_str} | Acc: {acc_str} | PP: {cur_pp}/{base_pp}\n"
                f"    {mdesc}\n"
            )

        lines.append("\n")

    return "\n".join(lines)


def _fmt_weather(weather: int, turns_left: int | None) -> str:
    if weather & 0x08:
        return "Sandstorm (permanent)" if turns_left is None else f"Sandstorm ({turns_left} turns remaining)"
    return "None"


def _fmt_hazards(h: SideHazards) -> str:
    parts = []
    if h.stealth_rock:
        parts.append("Stealth Rock")
    if h.spikes:
        parts.append(f"Spikes ×{h.spikes}")
    if h.toxic_spikes:
        parts.append(f"Toxic Spikes ×{h.toxic_spikes}")
    return ", ".join(parts) or "None"


def _render_transcript(steps: list[StepLog], party_names: list[str], show_deltas: bool = True) -> str:
    """Render steps as the verbatim on-screen battle text, one message per line.

    With show_deltas, each message is annotated with the HP that changed while it was
    displayed (diffed against the previous message; the opponent baseline resets when
    Giovanni switches). HP is keyed by name, so this is robust to the EWRAM party
    reordering that happens during a faint. Who moved first is intentionally NOT shown —
    the message order already conveys it; current stat stages live in the state block.
    """
    lines: list[str] = []
    prev_party: dict | None = None
    prev_opp: tuple | None = None  # (species, current_hp)
    for step in steps:
        lines.append("Battle start:" if step.step == 0 else f"Turn {step.step} — you chose {step.action}:")
        if not step.messages:
            lines.append("    (no text captured)")
        for ev in step.messages:
            parts = []
            if show_deltas:
                if prev_party is not None:
                    for name, (cur, _mx) in ev.party_hp.items():
                        pc = prev_party.get(name, (cur, 0))[0]
                        if cur != pc:
                            parts.append(f"{name} {pc}→{cur} HP")
                if (ev.opp_hp is not None and prev_opp is not None
                        and prev_opp[0] == ev.opp_species and prev_opp[1] != ev.opp_hp[0]):
                    parts.append(f"{ev.opp_species} {prev_opp[1]}→{ev.opp_hp[0]} HP")
            annotation = "   [" + ", ".join(parts) + "]" if parts else ""
            lines.append(f"    {ev.text}{annotation}")
            prev_party = ev.party_hp
            if ev.opp_hp is not None:
                prev_opp = (ev.opp_species, ev.opp_hp[0])
    return "\n".join(lines)


def _fmt_ev_spread(evs: dict) -> str:
    parts = [f"{stat} {ev}" for stat, ev in evs.items() if ev]
    return ", ".join(parts) if parts else "no EVs"


def _fmt_episode(episode: EpisodeRecord) -> str:
    outcome = "WIN" if episode.won else "LOSS"
    header = (f"Episode {episode.episode_num} ({outcome}, {episode.turns} turns, "
              f"{episode.pokemon_remaining} Pokemon remaining):")

    # Per-episode config (the variables that change between episodes). The static team
    # sheet — moves, base stats, abilities — is shown once in YOUR TEAM, not repeated here.
    config_lines = []
    if episode.lead:
        config_lines.append(f"Lead: {episode.lead}")
    if episode.ev_spreads:
        spread = "; ".join(f"{name} ({_fmt_ev_spread(evs)})" for name, evs in episode.ev_spreads)
        config_lines.append(f"EV spreads: {spread}")
    config_text = ("\n".join(config_lines) + "\n") if config_lines else ""

    return header + "\n" + config_text + _render_transcript(episode.steps, episode.party_names, show_deltas=False)


def build_opp_discovery_text(
    history: list[StepLog],
    prior_episodes: list[EpisodeRecord],
    current_opp_species: str = "",
    current_opp_ability: str = "",
    current_opp_hp: int | None = None,
    current_opp_max_hp: int | None = None,
) -> str:
    """Build a partial Giovanni team sheet from what has been discovered in battle."""
    seen: dict[str, dict] = {}

    def record(species: str, ability: str, move_id: int) -> None:
        if not species:
            return
        if species not in seen:
            seen[species] = {"ability": "", "moves": []}
        if ability and not seen[species]["ability"]:
            seen[species]["ability"] = ability
        move = MOVE_NAME.get(move_id) if move_id else None
        if move and move not in seen[species]["moves"]:
            seen[species]["moves"].append(move)

    for episode in prior_episodes:
        for step in episode.steps:
            record(step.opp_species, step.opp_ability, step.opponent_move)

    for step in history:
        record(step.opp_species, step.opp_ability, step.opponent_move)

    if current_opp_species:
        if current_opp_species not in seen:
            seen[current_opp_species] = {"ability": "", "moves": []}
        if current_opp_ability and not seen[current_opp_species]["ability"]:
            seen[current_opp_species]["ability"] = current_opp_ability

    if not seen:
        return "No information yet — opponent's team is unknown."

    lines = []
    for name, info in seen.items():
        is_active = name == current_opp_species
        active_marker = " **(active)**" if is_active else ""
        lines.append(f"## {name}{active_marker}")
        lines.append(f"**Ability:** {info['ability'] or '?'}")
        if is_active:
            if current_opp_hp is not None and current_opp_max_hp is not None:
                lines.append(f"**HP:** {current_opp_hp}/{current_opp_max_hp}")
            elif current_opp_hp is not None:
                lines.append(f"**HP:** {current_opp_hp}/? (max offset unverified — run scripts/find_opp_hp.py)")
            else:
                lines.append("**HP:** ?")
        else:
            lines.append("**HP:** (not active)")
        lines.append("**Moves:**")
        for move_name in info["moves"]:
            move_id = next((i for i, m in MOVE_DATA.items() if m["name"] == move_name), None)
            if move_id is not None:
                m = MOVE_DATA[move_id]
                power = str(m["power"]) if m["power"] is not None else "—"
                acc   = f"{m['accuracy']}%" if m["accuracy"] is not None else "—"
                lines.append(f"  - **{move_name}** | {m['type']} | {m['category']} | Power: {power} | Acc: {acc} | PP: {m['pp']}")
                if m.get("description"):
                    lines.append(f"    {m['description']}")
            else:
                lines.append(f"  - {move_name}")
        for _ in range(4 - len(info["moves"])):
            lines.append("  - ?")
        lines.append("")

    return "\n".join(lines).rstrip()


def build_lead_context(team: str, prior_episodes: list[EpisodeRecord]) -> str:
    opp_text = build_opp_discovery_text([], prior_episodes)
    prior = "\n\n".join(_fmt_episode(a) for a in prior_episodes) if prior_episodes else "None"
    return (
        f"YOUR TEAM:\n{team}\n\n"
        f"OPPONENT'S TEAM (discovered so far):\n{opp_text}\n\n"
        f"PRIOR EPISODES:\n{prior}\n\n"
        f"TASK:\n"
        f"Respond with only the name of the Pokemon you want to lead with "
        f"(one of the names from YOUR TEAM above, spelled exactly)."
    )


def build_action_context(
    state: BattleState,
    history: list[StepLog],
    team: str,
    prior_episodes: list[EpisodeRecord],
) -> str:
    stat_labels = ["ATK", "DEF", "SPE", "SPA", "SPD", "ACC", "EVA"]

    def fmt_stages(raw):
        parts = []
        for label, r in zip(stat_labels, raw):
            n = r - 6
            parts.append(f"{label} {'+' if n >= 0 else ''}{n}")
        return ", ".join(parts)

    active = state.party[state.active_slot]
    state_lines = [
        f"Active Pokemon: {active.name}",
        f"Giovanni's active Pokemon: {state.opp_species}",
        "",
        "Party:",
    ]
    for p in state.party:
        status_str = f" [{p.status}]" if p.status else ""
        state_lines.append(f"  {p.name}: {p.current_hp}/{p.max_hp} HP{status_str}")
    state_lines.append(f"\nWeather: {_fmt_weather(state.weather, state.weather_turns_left)}")
    state_lines.append(f"Hazards (your side): {_fmt_hazards(state.hazards_player)}")
    state_lines.append(f"Hazards (opponent's side): {_fmt_hazards(state.hazards_opp)}")
    state_lines.append(f"Your stat stages: {fmt_stages(state.stat_stages)}")
    state_lines.append(f"Opponent stat stages: {fmt_stages(state.opp_stat_stages)}")

    party_names = [p.name for p in state.party]
    if not history:
        history_text = "No turns yet (battle just started)."
    else:
        history_text = _render_transcript(history, party_names, show_deltas=True)

    opp_text = build_opp_discovery_text(
        history, prior_episodes, state.opp_species, state.opp_ability,
        state.opp_current_hp, state.opp_max_hp
    )
    prior = "\n\n".join(_fmt_episode(a) for a in prior_episodes) if prior_episodes else "None"
    state_text = "\n".join(state_lines)

    return (
        f"YOUR TEAM:\n{team}\n\n"
        f"OPPONENT'S TEAM (discovered so far):\n{opp_text}\n\n"
        f"CURRENT BATTLE STATE:\n{state_text}\n\n"
        f"BATTLE HISTORY (this episode):\n{history_text}\n\n"
        f"PRIOR EPISODES:\n{prior}\n\n"
        f"TASK:\n"
        f"Choose one action. Respond with exactly one line:\n"
        f'  FIGHT <move_name>      — use a move (e.g. "FIGHT Earthquake")\n'
        f'  SWITCH <pokemon_name>  — voluntary switch (e.g. "SWITCH Gyarados")'
    )


def build_replacement_context(
    state: BattleState,
    history: list[StepLog],
    team: str,
    prior_episodes: list[EpisodeRecord],
) -> str:
    stat_labels = ["ATK", "DEF", "SPE", "SPA", "SPD", "ACC", "EVA"]

    def fmt_stages(raw):
        parts = []
        for label, r in zip(stat_labels, raw):
            n = r - 6
            parts.append(f"{label} {'+' if n >= 0 else ''}{n}")
        return ", ".join(parts)

    state_lines = [
        f"Giovanni's active Pokemon: {state.opp_species}",
        "",
        "Party:",
    ]
    for p in state.party:
        status_str = f" [{p.status}]" if p.status else ""
        fainted_str = " (fainted)" if p.current_hp == 0 else ""
        state_lines.append(f"  {p.name}: {p.current_hp}/{p.max_hp} HP{status_str}{fainted_str}")
    state_lines.append(f"\nWeather: {_fmt_weather(state.weather, state.weather_turns_left)}")
    state_lines.append(f"Hazards (your side): {_fmt_hazards(state.hazards_player)}")
    state_lines.append(f"Opponent stat stages: {fmt_stages(state.opp_stat_stages)}")

    party_names = [p.name for p in state.party]
    if not history:
        history_text = "No turns yet."
    else:
        history_text = _render_transcript(history, party_names, show_deltas=True)

    opp_text = build_opp_discovery_text(
        history, prior_episodes, state.opp_species, state.opp_ability,
        state.opp_current_hp, state.opp_max_hp
    )
    prior = "\n\n".join(_fmt_episode(a) for a in prior_episodes) if prior_episodes else "None"
    state_text = "\n".join(state_lines)

    return (
        f"YOUR TEAM:\n{team}\n\n"
        f"OPPONENT'S TEAM (discovered so far):\n{opp_text}\n\n"
        f"CURRENT BATTLE STATE:\n{state_text}\n\n"
        f"BATTLE HISTORY (this episode):\n{history_text}\n\n"
        f"PRIOR EPISODES:\n{prior}\n\n"
        f"TASK:\n"
        f"Your active Pokemon has fainted. Choose a replacement from your surviving party members.\n"
        f'Respond with only the Pokemon name (e.g. "Gyarados").'
    )

def build_propose_team_context(
    team: str,
    prior_episodes: list[EpisodeRecord],
) -> str:
    prior = "\n\n".join(_fmt_episode(a) for a in prior_episodes) if prior_episodes else "None"

    pokemon_names = [line[3:].strip() for line in team.split('\n') if line.startswith('## ')]
    ev_format_lines = '\n'.join(
        f'  {name}: HP <n>, ATK <n>, DEF <n>, SPATK <n>, SPDEF <n>, SPD <n>'
        for name in pokemon_names
    )

    return (
        f"YOUR TEAM (with current EV allocations):\n{team}\n\n"
        f"PRIOR EPISODES:\n{prior}\n\n"
        f"TASK:\n"
        f"Propose new EV allocations for each Pokemon based on what problems the team is facing.\n"
        f"EV rules: max 252 per stat, max 508 total per Pokemon, use multiples of 4.\n\n"
        f"Respond with one line per Pokemon in the order above:\n"
        f"{ev_format_lines}"
    )
