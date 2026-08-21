# Tasks

## Overview

This directory contains all the tasks in the benchmark, with each being its own directory. The layout for each task looks like this:

```bash
<task_name>/
    data/
        agent/              -> all the JSON data the agent has access to in its container
        validation/         -> data needed by the server to validate agent requests for this task
    environment/
        battle-server/      -> define server container
        Dockerfile          -> define agent container
        docker-compose.yaml -> build both
    tests/                  -> validates agent trajectory to see if it won or lost
    instruction.md          -> agent initial prompt
    save_state.ss0          -> save state of the task
    task.toml               -> Harbor task config details
    task.yaml               -> Benchmark task config details
```

## Make your own Task

Assuming you are running the game via mgba in the project root, follow these steps:

0. Ensure you are in a spot in the game where a simple sequence of key presses can trigger the pre-battle dialogue (e.g. you're right next to the opponent, or walking left for 2 seconds triggers the encounter)
1. Create a quicksave state (you should see a file called `radicalred.ss1` created).
2. Run `uv run scripts/export_mgba_slot_state.py` to produce a file `save_state.ss0`. This is what the battle server will load.
3. Create a new directory in `tasks/` for your task. Move `save_state.ss0` into it and make a `task.toml` file. You can just copy an existing one and change the name/description fields.
4. Add your task to `data/radical_red/v4.1/progression.json`. This file is an ordered list of all the encounters in the game, which we use to progressively gate given items/TMs.
5. Create your `task.yaml`, which will contain details like the level cap of your task, maximum team size, which team modifications are allowed, etc. The tricky parts are `battle_trigger` which is the sequence of key presses determined in step 0, and `allowed_locations`/`available_water_methods` which determine what Pokemon/items/moves the agent ahs access to.
6. Copy an `instruction.md` from an existing task and update it for your task. It's pretty modular, so all you need to change are a few bits about level cap/party size restrictions.
7. Run `uv run scripts/build_task_data.py tasks/<task_name>` to generate the static data for your task.

