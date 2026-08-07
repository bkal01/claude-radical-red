# Giovanni ability optimization task

Defeat the configured Giovanni team in Pokemon Radical Red. You construct your
player team, then control its abilities and have the configured episode budget to win.
Use only the battle-server MCP tools for game interaction; do not try to access
the ROM, emulator, or battle internals.

Before acting, use the reference data to construct a six-Pokemon team and call `apply_team`.
You receive no roster or battle information before that call; the inclusive level cap is 57.
Keep notes, experiments, and learned action sequences in `/workspace/scratch`;
that directory persists across resets within the trial.

## MCP tools

The battle-server provides these tools:

- `observe()` returns the current observation and is read-only.
- `team()` returns the configured team and calculated stats.
- `lead(pokemon)` starts an episode with the named Pokemon as the lead after setup.
- `action(command)` takes one battle action.
- `apply_team(team)` configures the initial team, or updates abilities and starts the next episode.
- `reset()` restores the battle fixture and starts the next episode.

Tool responses contain `ok: true` on success. An unsuccessful response has
`ok: false` and an `error` message; invalid calls do not change game state.
Calls are rejected after the trial is complete.

## Phases and battle actions

The observation's `phase` is one of the following:

- `awaiting_team`: call `apply_team()` with a valid complete team. `lead()`,
  `action()`, and `reset()` are not legal.
- `no_battle`: call `lead(pokemon)` to begin an episode. `team()` and
  `observe()` are also legal.
- `in_battle`: call `action()` with one of:
  - `FIGHT <move>` to use a move known by the active Pokemon.
  - `SWITCH <pokemon>` to switch to a non-fainted Pokemon. This is legal when
    the active Pokemon has not fainted.
  - `SEND <pokemon>` to replace a fainted active Pokemon. `SEND` is required
    when the observation has `needs_replacement: true` and is otherwise
    illegal.
- `ended`: the battle has ended. The final action response includes `ended: true`,
  `won`, messages, and the terminal observation.

`observe()` is read-only and may be called in any phase while the trial is
still active. `team()` may also be called in any phase. The current observation
includes the active Pokemon, party HP/status/moves, opponent species and HP,
weather, hazards, and stat stages.

## Episodes and reset

An episode is one attempt from the original battle fixture. A valid initial
`apply_team()` prepares episode 1 without consuming it. Calling `lead()` starts
the battle for the current episode.

`reset()` restores the original battle state, clears the current battle
session, and advances to the next episode. It consumes an episode even when
called before the current battle ends. A reset is rejected once the episode
budget is exhausted.

Stop after the environment reports a win, the episode budget is exhausted, or
an unrecoverable environment error occurs.

## Team Updates

The first `apply_team()` must construct all six Pokemon with the neutral Hardy
Nature (`nature_id` 0). Every member must specify a `level` from 1 through the inclusive cap of
57. Each initial member must specify `slot`, `species_id`, `level`,
`nature_id`, `ability_id`, `move_ids`, `held_item_id`, and `evs`.
After setup, this task permits Ability updates. Call `apply_team()` during a live
battle or after a lost episode in the place of `reset()`. A successful update
automatically restores the battle fixture, advances to the next episode, and
applies the accepted configuration. Invalid updates do not change the
configuration or advance the episode.

### Ability updates

Each `ability_id` must be a valid normal or hidden Ability for the Pokemon in
that slot. The available Ability IDs for a species are listed in
`species.json[species_id]`. Use `abilities.json[ability_id]` to look up an
Ability's name and description.

After setup, the argument must contain exactly one member entry for every current team slot
and must have this complete shape:

```json
{
  "members": [
    {
      "slot": 0,
      "species_id": 123,
      "level": 57,
      "ability_id": 65
    }
  ]
}
```

Use the active team returned by `team()` to determine the number of members,
their slots, their species IDs, and their current Abilities. Each slot must
appear exactly once, and its `species_id` must match the current member in
that slot. Every member must include `level` and `ability_id` exactly as
shown above.

## Reference data

The files in `/workspace/data` are JSON arrays indexed by game ID:

- `species.json[species_id]` contains a species name, form, source, types,
  base stats, and normal/hidden ability IDs. `source` is `official` or
  `radical_red`.
- `abilities.json[ability_id]` contains an ability name and description.
- `moves.json[move_id]` contains move information and can also be searched by
  move name.

The `team()` response includes species, move, and ability IDs and names. Use
the files to look up details when planning the battle, but use the MCP tools
for all game interaction.
