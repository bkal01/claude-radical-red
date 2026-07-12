import json

from rrbench.battle.engine import start_battle
from rrbench.battle.state import in_battle, read_battle_state
from rrbench.emulator.emulator import Emulator
from rrbench.emulator.memory import Party, PokemonNotInPartyError
from rrbench.interface.protocol import (
    render_observation,
    render_pre_battle,
    render_messages,
)

ROM_PATH = "radicalred.gba"
SAVE_STATE_PATH = "tasks/giovanni/save_state.ss0"

emu = Emulator(
    rom_path=ROM_PATH,
    save_state_path=SAVE_STATE_PATH
)
emu.load_state()


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