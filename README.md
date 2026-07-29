# claude-radical-red

## Overview

Pokemon Radical Red is a ROM hack of Pokemon FireRed, adding all Pokemon up to Gen 9 and incredibly difficult boss battles that require clever teambuilding and strategic play in order to win.

This project is a benchmark to see how good agents are at clearing Radical Red's boss battles.

## Benchmark Description

At the moment, we only have one boss battle: the fight against Giovanni in Silph Co. Tower, with a level cap of 57. Giovanni has a strong Rock/Ground based team, with a wide variety of secondary typings and coverage moves along with actually useful items. This is his team:

![](assets/giovanni-team.png)

The agent has access to this team:

![](assets/default_team.png)

<details>
<summary>Winning EV spreads</summary>

| Pokemon | HP | ATK | DEF | SPE | SPA | SPDEF |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Incineroar | 252 | 236 | 0 | 20 | 0 | 0 |
| Kingambit | 252 | 252 | 0 | 4 | 0 | 0 |
| Mawile | 4 | 252 | 0 | 252 | 0 | 0 |
| Tsareena | 252 | 252 | 0 | 4 | 0 | 0 |
| Armarouge | 252 | 0 | 4 | 0 | 252 | 0 |
| Gyarados | 252 | 252 | 0 | 4 | 0 | 0 |

</details>

All Pokemon are max level (57), and some have useful abilities/items. For example, Incineroar and Gyarados have Intimidate to cut the ATK stat of opposing Pokemon, Kingambit has Black Glasses to boost Dark type attacks, and Armarouge has the Weak Armor ability to potentially allow it to sweep with strategic switch-ins.

It took me ~6-8 hours to beat this battle, but a lot of that time was trying different Pokemon, items, moves, and abilities to produce a winning strategy for Giovanni. It's important to note that Giovanni's AI is is predictable. Given the exact same game state, the enemy AI will always perform the same action. The same attacks will crit and miss, and moves will do the exact same damage. This is exploitable: for example, if you know the opponent is going to use a Dragon-type move, you can switch into a Fairy-type Pokemon to avoid taking damage.

This turns boss battles into more of a search problem: can the agent find the right setup and sequence of actions to win? Once it finds a prefix of steps in an episode that makes progress towards the goal, it can reuse that prefix across episodes and build off of it.

## Setup

### 1. Install prerequisites

Install [uv](https://docs.astral.sh/uv/) and Docker, make sure Docker is
running, then install the Python dependencies:

```bash
uv sync
```

### 2. Add the ROM

It's illegal to distribute the ROM itself, so obtain it separately and place it
at `radicalred.gba` in the repository root. The committed task fixture starts
at the Giovanni battle.

### Optional: local emulator development

Coding-agent evaluations build mGBA inside the server image, so they do not need
host-side mGBA bindings. To run emulator code directly on macOS, build the local
bindings separately:

```bash
brew install ffmpeg cmake
bash scripts/install_mgba.sh
```

To play manually, install the mGBA application and open the ROM:

```bash
mgba radicalred.gba
```

mGBA picks up `radicalred.sav` automatically since it shares the same name as the ROM.

## Evaluation

Evaluations run through Harbor. The episode budget and optional video
recording are configured through environment variables:

```bash
RRBENCH_MAX_EPISODES=2 RRBENCH_RECORD=true \
  harbor run -p tasks/giovanni -a codex -m gpt-5.6-luna --env docker -n 1
```

Both values are passed to the battle server. When recording is enabled, Harbor
collects one MP4 per started episode as a `battle-server` artifact.


## Next Steps

In its current state, the benchmark is quite primitive. It would be nice to actually let the agent choose its team, abilities, items, moves, EV spreads, etc., which would expand the search space significantly and make the task a lot harder. Adding more battles would be great as well. Contributions are welcome to make this happen!
