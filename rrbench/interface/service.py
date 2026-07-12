import json
from pathlib import Path

from rrbench.battle.engine import start_battle, do_action
from rrbench.battle.state import in_battle, read_battle_state
from rrbench.emulator.emulator import Emulator
from rrbench.emulator.memory import Party, PokemonNotInPartyError
from rrbench.interface.protocol import (
    render_observation,
    render_pre_battle,
    render_messages,
)
from rrbench.tasks import TaskSpec, load_task


def create_emulator(task: TaskSpec) -> Emulator:
    emulator = Emulator(task.rom_path, task.save_state_path)
    emulator.load_state()
    return emulator


_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_TASK = load_task(
    _REPO_ROOT / "tasks/giovanni", rom_path=_REPO_ROOT / "radicalred.gba"
)
emu = create_emulator(_DEFAULT_TASK)


def observe() -> str:
    party = Party(emu.mem)
    if not in_battle(emu.mem):
        return json.dumps(render_pre_battle(party))
    return json.dumps(render_observation(read_battle_state(emu.mem, party)))

def lead(lead_pokemon: str) -> str:
    party = Party(emu.mem)
    try:
        session, state, messages = start_battle(emu, party, lead_pokemon)
    except PokemonNotInPartyError as e:
        return json.dumps({"error": str(e)})
    return json.dumps({"messages": render_messages(messages)})