from party import MOVE_DATA, MOVE_NAME
from battle import EpisodeRecord, BattleState, SideHazards, StepLog


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


def _fmt_episode(episode: EpisodeRecord) -> str:
    outcome = "WIN" if episode.won else "LOSS"
    lines = [
        f"Episode {episode.episode_num} ({outcome}, {episode.turns} turns, "
        f"{episode.pokemon_remaining} Pokemon remaining):"
    ]
    for s in episode.steps:
        opp_name = s.opp_species or "?"
        opp_move = (
            MOVE_NAME.get(s.opponent_move, f"move_{s.opponent_move}")
            if s.opponent_move
            else "—"
        )
        hp = ", ".join(
            f"{name} {cur}/{mx}" + (" (fainted)" if cur == 0 else "")
            for name, (cur, mx) in zip(episode.party_names, s.hp_snapshot)
        )
        order = ""
        if s.player_moved_first is True:
            order = " [player first]"
        elif s.player_moved_first is False:
            order = " [Giovanni first]"
        lines.append(
            f"  Turn {s.step}: {s.action} | Giovanni's {opp_name}: {opp_move}{order} | HP: [{hp}]"
        )
    return "\n".join(lines)


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
        hist_lines = []
        for s in history:
            opp_name = s.opp_species or "?"
            opp_move = (
                MOVE_NAME.get(s.opponent_move, f"move_{s.opponent_move}")
                if s.opponent_move
                else "—"
            )
            hp = ", ".join(
                f"{name} {cur}/{mx}" + (" (fainted)" if cur == 0 else "")
                for name, (cur, mx) in zip(party_names, s.hp_snapshot)
            )
            order = ""
            if s.player_moved_first is True:
                order = " [player first]"
            elif s.player_moved_first is False:
                order = " [Giovanni first]"
            hist_lines.append(
                f"  Turn {s.step}: {s.action} | Giovanni's {opp_name}: {opp_move}{order} | HP: [{hp}]"
            )
        history_text = "\n".join(hist_lines)

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
        hist_lines = []
        for s in history:
            opp_name = s.opp_species or "?"
            opp_move = (
                MOVE_NAME.get(s.opponent_move, f"move_{s.opponent_move}")
                if s.opponent_move
                else "—"
            )
            hp = ", ".join(
                f"{name} {cur}/{mx}" + (" (fainted)" if cur == 0 else "")
                for name, (cur, mx) in zip(party_names, s.hp_snapshot)
            )
            order = ""
            if s.player_moved_first is True:
                order = " [player first]"
            elif s.player_moved_first is False:
                order = " [Giovanni first]"
            hist_lines.append(
                f"  Turn {s.step}: {s.action} | Giovanni's {opp_name}: {opp_move}{order} | HP: [{hp}]"
            )
        history_text = "\n".join(hist_lines)

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
