# Giovanni battle task

Defeat the configured Giovanni team in Pokemon Radical Red. You control the
supplied player team and have the configured episode budget to win. Use only
the battle-server MCP tools for game interaction; do not try to access the ROM,
emulator, or battle internals.

Before acting, call `team` to inspect your current roster. Keep notes,
experiments, and learned action sequences in `/workspace/scratch`; that
directory persists across resets within the trial.

## MCP tools

The battle-server provides these tools:

- `observe()` returns the current observation and is read-only.
- `team()` returns the current team configuration and calculated stats.
- `lead(pokemon)` starts an episode with the named Pokemon as the lead.
- `action(command)` takes one battle action.
- `apply_team(team)` updates the team's EVs, Abilities, and moves and starts the next episode.
- `reset()` restores the battle fixture and starts the next episode.

Tool responses contain `ok: true` on success. An unsuccessful response has
`ok: false` and an `error` message; invalid calls do not change game state.
Calls are rejected after the trial is complete.

## Phases and battle actions

The observation's `phase` is one of the following:

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
  `won`, messages, and the terminal observation. A lost episode can be
  followed by `reset()` or `apply_team()` if another episode remains.

`observe()` is read-only and may be called in any phase while the trial is
still active. `team()` may also be called in any phase. The current observation
includes the active Pokemon, party HP/status/moves, opponent species and HP,
weather, hazards, and stat stages.

## Episodes and reset

An episode is one attempt from the original battle fixture. The trial starts
in episode 1. Calling `lead()` starts the battle for the current episode.

`reset()` restores the original battle state, clears the current battle
session, and advances to the next episode. It consumes an episode even when
called before the current battle ends. A reset is rejected once the episode
budget is exhausted.

Stop after the environment reports a win, the episode budget is exhausted, or
an unrecoverable environment error occurs.

## Team updates

This task permits EV, Ability, and move updates. Call `apply_team()` during a live
battle or after a lost episode in the place of `reset()`. A successful update
automatically restores the battle fixture, advances to the next episode, and
applies the accepted configuration. Invalid updates do not change the
configuration or advance the episode.

### EV updates

Each EV value must be an integer from 0 through 252, divisible by four, with
at most 508 total EVs per Pokemon. The `evs` object must contain exactly `HP`,
`ATK`, `DEF`, `SPE`, `SPA`, and `SPDEF`.

### Ability updates

Each `ability_id` must be a valid normal or hidden Ability for the Pokemon in
that slot. The available Ability IDs for a species are listed in
`species.json[species_id]`. Use `abilities.json[ability_id]` to look up an
Ability's name and description.

### Move updates

Each `move_ids` value must be an array of exactly four integer move IDs. Each
move must be learnable by the Pokemon in that slot according to
`learnsets.json[species_id]`. This task has an inclusive level cap of 57:
level-up moves are valid only when their required level is 57 or lower. Moves
listed under `tm_hm`, `tutor`, `egg`, `pre_evolution`, or `event` are also
valid.

The argument must contain exactly one member entry for every current team slot
and must have this complete shape:

```json
{
  "members": [
    {
      "slot": 0,
      "species_id": 123,
      "ability_id": 65,
      "move_ids": [33, 45, 73, 345],
      "evs": {
        "HP": 252,
        "ATK": 0,
        "DEF": 4,
        "SPE": 0,
        "SPA": 0,
        "SPDEF": 252
      }
    }
  ]
}
```

Use the active team returned by `team()` to determine the number of members,
their slots, their species IDs, their current Abilities, and their current
moves. Each slot must appear exactly once, and its `species_id` must match the
current member in that slot. Every member must include `ability_id`,
`move_ids`, and `evs` exactly as shown above.

## Reference data

The files in `/workspace/data` are JSON arrays indexed by game ID:

- `species.json[species_id]` contains a species name, types, base stats, and
  normal/hidden ability IDs.
- `moves.json[move_id]` contains move information and can also be searched by
  move name.
- `abilities.json[ability_id]` contains an ability name and description and
  can also be searched by name.
- `learnsets.json[species_id]` contains that species' learnable move IDs. Its
  `level_up` entries contain `move_id` and required `level`; `tm_hm`, `tutor`,
  `egg`, `pre_evolution`, and `event` contain move-ID arrays for their
  respective acquisition methods.

The `team()` response includes species, move, and ability IDs and names. Use
the files to look up details when planning the battle, but use the MCP tools
for all game interaction.
