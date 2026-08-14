# Pokemon Battle task

Defeat the configured opposing Pokemon team in a Singles battle. You must construct your player team before
the first battle and have the configured episode budget to win. Use only
the battle-server MCP tools for game interaction; do not try to access the ROM,
emulator, or battle internals.

Before acting, use the reference data to construct a team and call `apply_team`.
You receive no player roster or battle information before that call; only this
task's inclusive level cap of 57 applies. Keep notes,
experiments, and learned action sequences in `/workspace/scratch`; that
directory persists across resets within the trial.

## MCP tools

The battle-server provides these tools:

- `observe()` returns the current observation and is read-only.
- `team()` returns the configured team and calculated stats.
- `lead(pokemon)` starts an episode with the named Pokemon as the lead after setup.
- `action(command)` takes one battle action.
- `apply_team(team)` configures the initial team, or updates the team and starts the next episode.
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
  `won`, messages, and the terminal observation. A lost episode can be
  followed by `reset()` or `apply_team()` if another episode remains.

For Pokemon with a non-null `form`, use `<name>-<form>` as the Pokemon argument
to `SWITCH` and `SEND`; for example, `SWITCH Rotom-wash`. For Pokemon whose
`form` is null, use its name alone.

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

## Team updates

The first `apply_team()` must construct all four Pokemon. This task uses four party slots.
After setup, this task permits Pokemon, EV, Ability, Nature, move, and item updates. Call `apply_team()` during a live
battle or after a lost episode in the place of `reset()`. A successful update
automatically restores the battle fixture, advances to the next episode, and
applies the accepted configuration. Invalid updates do not change the
configuration or advance the episode.

### Pokemon updates

Each `species_id` must be an available Pokemon in `species.json`; the task
provides entries only for Pokemon obtainable from its permitted locations and
their level-cap-eligible evolutions; Mega forms are excluded. Its
`minimum_level` must not exceed this task's inclusive level cap of 57. Initial
team members must each specify an
integer `level` from 1 through 57. The level can be lower than the cap. Initial
team members must specify a valid Nature;
their Ability and moves must be valid for the chosen species. After setup, a
chosen Pokemon retains its slot's level and Nature.

### EV updates

Each EV value must be an integer from 0 through 252, divisible by four, with
at most 508 total EVs per Pokemon. The `evs` object must contain exactly `HP`,
`ATK`, `DEF`, `SPE`, `SPA`, and `SPDEF`.

### Ability updates

Each `ability_id` must be a valid normal or hidden Ability for the Pokemon in
that slot. The available Ability IDs for a species are listed in
`species.json[species_id]`. Use `abilities.json[ability_id]` to look up an
Ability's name and description.

### Nature updates

Each `nature_id` must be an integer from 0 through 24. Changing a Nature does
not change the Pokemon's Ability.

### Move updates

Each `move_ids` value must be an array of exactly four integer move IDs. Each
move must be learnable by the Pokemon in that slot according to
`learnsets.json[species_id]`. This task has an inclusive level cap of 57:
level-up moves are valid only when their required level is 57 or lower. Moves
listed under `tm_hm`, `tutor`, `egg`, `pre_evolution`, or `event` are also
valid. A Pokemon may also use moves available to any of its recursive
pre-evolutions; apply the same rules at every entry named by
`pre_evolution_ids`.

### Item updates

Each `held_item_id` must be `0` or match the `id` field of an entry in
`items.json`. No item may be assigned to more Pokemon than its `count` in that
file. Use the matching entry to look up an item's name and description.
An ID of `0` means the Pokemon has no held item.

The argument must contain exactly one member entry for every current team slot
and must have this complete shape:

```json
{
  "members": [
    {
      "slot": 0,
      "species_id": 123,
      "level": 57,
      "nature_id": 3,
      "ability_id": 65,
      "move_ids": [33, 45, 73, 345],
      "held_item_id": 711,
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

The initial call must contain exactly four members, one for each slot from 0
through 3. After setup, use the active team returned by `team()` to determine
the number of members, their
slots, their current species IDs, Abilities, moves, and held item IDs. Each
slot must appear exactly once. Every member must include `species_id`, `level`,
`nature_id`, `ability_id`, `move_ids`, `held_item_id`, and `evs` exactly as
shown above.

## Reference data

The files in `/workspace/data` are JSON arrays. `species.json`, `learnsets.json`,
and `items.json` contain entries only for data available to this task;
`moves.json` and `abilities.json` contain complete game data needed to build
legal teams. Species, moves, abilities, and learnsets are indexed by game ID;
each item record instead includes its explicit `id`.

- `species.json[species_id]` contains a species name, form, source, types,
  base stats, and normal/hidden ability IDs.
- `moves.json[move_id]` contains move information and can also be searched by
  move name.
- `abilities.json[ability_id]` contains an ability name and description and
  can also be searched by name.
- `items.json` contains an `id`, name, description, and available `count` for
  each item available to this task.
- `learnsets.json[species_id]` contains that species' learnable move IDs. Its
  `level_up` entries contain `move_id` and required `level`; `tm_hm`, `tutor`,
  `egg`, `pre_evolution`, and `event` contain move-ID arrays for their
  respective acquisition methods. `pre_evolution_ids` contains direct prior
  species IDs; follow it recursively when considering inherited moves.

The `team()` response includes species, move, ability, and held-item IDs and
names. Use the files to look up details when planning the battle, but use the
MCP tools for all game interaction.
