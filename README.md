# claude-radical-red

## Overview

Pokemon Radical Red is a ROM hack of Pokemon FireRed, adding all Pokemon up to Gen 9 and incredibly difficult boss battles that require clever teambuilding and strategic play in order to win.

This benchmark extracts battles from Radical Red (specifically ones of "mini-boss" difficulty and above) and evaluates whether or not coding agents can find a team and sequence of moves that wins.

## Benchmark Description

We have 21 live tasks at the moment, spanning from the very first rival battle all the way up to Giovanni at Silph Co. Tower. Each task has a level cap and a set of Pokemon/moves/items that the agent is able to build their team with, determined by what's available in-game at the point of the battle. For added difficulty, we restrict the maximum party size to the number of Pokemon used by the opponent.

We also have a special task (`ghost-pokemon-tower`) where the agent needs to win against a boosted Alolan-Marowak under unique battle conditions. Since this task is a slightly different format (and much harder) than normal Radical Red boss battles, we treat this task as separate, mostly as a qualitative way to see if agents do anything interesting.

When running a task, the agent is dropped into a sandbox containing JSON data of Pokemon, items, moves, and abilities for the task. The agent must grep through this data, understand what's available to it, and build a strong team with no knowledge of the opponent's team.

Then, the agent battles against the opponent. As it does, it gleans information about the enemy team composition, speed tiers, held items, etc. The process of the agent proposing a team and battling the opponent is called an *episode*. After each episode, the agent is given the opportunity to analyze the battle history to update its team and try again, up to a maximum episode cap.

Although this benchmark is for coding agents, it's not a "coding agent benchmark" per se. There are no difficult coding tasks required to participate/succeed in tasks here. All the agent needs to be able to do is analyze JSON data and make repeated calls to an MCP server, which are well within the capabilities of current frontier coding agents. Instead, this benchmark evaluates how efficiently agents gather information and adapt in an unknown environment and whether they can find creative solutions to difficult problems.

## Setup

### 1. Install prerequisites

Install [uv](https://docs.astral.sh/uv/) and Docker, make sure Docker is
running, then install the Python dependencies:

```bash
uv sync
```

### 2. Add the ROM

It's illegal to distribute the ROM itself, so obtain it separately and place it
at `radicalred.gba` in the repository root.

### Optional: local emulator development

Coding-agent evaluations build mGBA inside the server image, so they do not need
host-side mGBA bindings. To run emulator code directly on your machine, run

```bash
brew install ffmpeg cmake
bash scripts/install_mgba.sh
```

To play manually, install the mGBA application and open the ROM:

```bash
mgba radicalred.gba
```

^ this is macOS specific at the moment.

mGBA picks up `radicalred.sav` automatically since it shares the same name as the ROM.
The committed save state starts the user just before the Giovanni at Silph Co. fight.

## Tests

Run the test suite through the project’s `uv` environment:

```bash
uv run pytest -q
```

To run the fast tests without the real-ROM MCP integration test:

```bash
uv run pytest -q -m "not integration"
```

## Evaluation

We use [Harbor](https://www.harborframework.com/) for evaluations.

Before running any evaluations, authenticate with the agent provider you want to eval:
- API keys: set `ANTHROPIC_API_KEY` for Claude Code, `OPENAI_API_KEY` for Codex
- Claude Code subscription: see [docs](https://code.claude.com/docs/en/authentication). set `CLAUDE_CODE_OAUTH_TOKEN` and `CLAUDE_FORCE_OAUTH=1`
- Codex subscription: see [docs](https://developers.openai.com/codex/auth). run `codex login` then ensure `CODEX_FORCE_AUTH_JSON=1` when calling `harbor run`

Then, run the following command to evaluate `<coding_agent_name>` with model `<model_name>`
on `<task_name>` with a maximum episode cap of `<N>`:

```bash
RRBENCH_MAX_EPISODES=<N> \
harbor run \
  --path tasks/<task_name> \
  --agent <coding_agent_name> \
  --model <model_name> \
  --env docker \
  --n-concurrent 1
```

You can run `harbor view jobs` in a separate terminal to spin up a webserver where you can view
job logs and the progress of the current job. Logs are stored in `jobs/`.

### Replays

For the sake of evaluation speed, we do not record video of the battle while an agent engages in a task.
To get video, run:

```bash
uv run scripts/replay_job.py <job_id>
```

`<job_id>` is found in the `result.json` of your Harbor job. This script deterministically replays the entire trial, including losses + resets, and repeatedly captures screenshots to produce a recording. The recording of each episode is
stored in `jobs/<trial_name>/artifacts/var/log/battle/videos/`.

### Play a Task Yourself

Coming soon!


## Next Steps

There's a lot more to do to expand this benchmark! We've only mapped out ~1/2 of the game, and it's the easy half. There are more battles to be added, more mechanics (Mega Evolution, Doubles battles, etc.), and more coding agents that need to be evaluated. Contributions are welcome!