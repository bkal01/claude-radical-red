# Giovanni item optimization task

Defeat the configured Giovanni team in Pokemon Radical Red. You control the
supplied player team's items and have the configured episode budget to win. Use only
the battle-server MCP tools for game interaction; do not try to access the ROM,
emulator, or battle internals.

Before acting, call `team` to inspect your current roster and its held items. Keep notes,
experiments, and learned action sequences in `/workspace/scratch`; that
directory persists across resets within the trial.

## MCP tools

The battle-server provides these tools:

- `observe()` returns the current observation and is read-only.
- `team()` returns the current team configuration and calculated stats.
- `lead(pokemon)` starts an episode with the named Pokemon as the lead.
- `action(command)` takes one battle action.
- `apply_team(team)` updates the team's items and starts the next episode.
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

This task permits item updates. Call `apply_team()` during a live
battle or after a lost episode in the place of `reset()`. A successful update
automatically restores the battle fixture, advances to the next episode, and
applies the accepted configuration. Invalid updates do not change the
configuration or advance the episode.

### Item updates

Each `held_item_id` must be a valid item ID. Use `items.json[held_item_id]`
to look up an item's name and description. An ID of `0` means the Pokemon has
no held item.

The argument must contain exactly one member entry for every current team slot
and must have this complete shape:

```json
{
  "members": [
    {
      "slot": 0,
      "species_id": 123,
      "held_item_id": 711
    }
  ]
}
```

Use the active team returned by `team()` to determine the number of members,
their slots, their species IDs, and their current held item IDs. Each slot
must appear exactly once, and its `species_id` must match the current member in
that slot. Every member must include `held_item_id` exactly as shown above.

## Reference data

The files in `/workspace/data` are JSON arrays indexed by game ID:

- `items.json[held_item_id]` contains an item name and description and can
  also be searched by name.

The `team()` response includes held-item IDs. Use the file to look up details
when planning the battle, but use the MCP tools for all game interaction.
