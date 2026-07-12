from rrbench.battle.engine import start_battle, do_action
from rrbench.battle.state import BattleSession, in_battle, read_battle_state
from rrbench.emulator.emulator import Emulator
from rrbench.emulator.memory import Party, PokemonNotInPartyError
from rrbench.interface.protocol import (
    render_observation,
    render_pre_battle,
    render_messages,
)
from rrbench.tasks import TaskSpec


def create_emulator(task: TaskSpec) -> Emulator:
    emulator = Emulator(task.rom_path, task.save_state_path)
    emulator.load_state()
    return emulator


class BattleService:
    """
    Persistent Service that holds the state of a Task, takes in agent actions,
    and returns the corresponding output back to the agent.
    """

    def __init__(self, task: TaskSpec) -> None:
        self.task = task
        self.emu = create_emulator(task)
        self.session: BattleSession | None = None

    def observe(self) -> dict:
        party = Party(self.emu.mem)
        if not in_battle(self.emu.mem):
            observation = render_pre_battle(party)
        else:
            observation = render_observation(read_battle_state(self.emu.mem, party))
        return {"ok": True, "observation": observation}

    def lead(self, lead_pokemon: str) -> dict:
        party = Party(self.emu.mem)
        try:
            self.session, state, messages = start_battle(self.emu, party, lead_pokemon)
        except PokemonNotInPartyError as e:
            return {"ok": False, "error": str(e)}
        return {
            "ok": True,
            "messages": render_messages(messages),
            "observation": render_observation(state),
            "ended": self.session.ended,
            "won": self.session.won,
        }
