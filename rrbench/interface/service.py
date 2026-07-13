from rrbench.battle.engine import start_battle, do_action
from rrbench.battle.state import BattleSession, in_battle, read_battle_state
from rrbench.emulator.emulator import Emulator
from rrbench.emulator.memory import (
    Party,
    PokemonFaintedError,
    PokemonNotInPartyError,
)
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
        self.terminal_observation: dict | None = None

    def observe(self) -> dict:
        if self.session is not None and self.session.ended:
            return {"ok": True, "observation": self.terminal_observation}

        battle_active = in_battle(self.emu.mem)
        if battle_active and self.session is not None:
            party = self.session.party
            party.refresh()
        else:
            party = Party(self.emu.mem)

        if not battle_active:
            observation = render_pre_battle(party)
        else:
            observation = render_observation(read_battle_state(self.emu.mem, party))
        return {"ok": True, "observation": observation}

    def lead(self, lead_pokemon: str) -> dict:
        if self.session is not None or in_battle(self.emu.mem):
            return {"ok": False, "error": "lead is only valid in no_battle phase"}

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

    def action(self, command: str) -> dict:
        if self.session is None or self.session.ended or not in_battle(self.emu.mem):
            return {"ok": False, "error": "action is only valid in a live battle"}

        command_parts = command.strip().split(maxsplit=1)
        if len(command_parts) != 2 or not command_parts[1]:
            return {"ok": False, "error": "action must be FIGHT, SWITCH, or SEND followed by a name"}

        action_type, action_arg = command_parts
        if action_type not in {"FIGHT", "SWITCH", "SEND"}:
            return {"ok": False, "error": f"unknown action type: {action_type!r}"}

        party = self.session.party
        party.refresh()
        state = read_battle_state(self.emu.mem, party)

        if state.needs_replacement and action_type != "SEND":
            return {"ok": False, "error": "SEND is required when the active Pokemon has fainted"}
        if not state.needs_replacement and action_type == "SEND":
            return {"ok": False, "error": "SEND is only valid when the active Pokemon has fainted"}

        if action_type == "FIGHT":
            active = party.members[state.active_slot]
            if action_arg not in active.moves:
                return {"ok": False, "error": f"{active.name} does not know {action_arg!r}"}
            move_slot = active.moves.index(action_arg)
            if active.pp[move_slot] == 0:
                return {"ok": False, "error": f"{active.name} has no PP remaining for {action_arg!r}"}
        else:
            if action_type == "SWITCH" and action_arg == party.members[state.active_slot].name:
                return {"ok": False, "error": "cannot switch to the active Pokemon"}
            try:
                party.resolve_switch_target(action_arg)
            except (PokemonNotInPartyError, PokemonFaintedError) as error:
                return {"ok": False, "error": str(error)}

        self.session, state, step_log = do_action(
            self.emu,
            self.session.party,
            self.session,
            action_type,
            action_arg,
        )
        observation = render_observation(state)
        if self.session.ended:
            observation["phase"] = "ended"
            observation["won"] = self.session.won
            self.terminal_observation = observation
        return {
            "ok": True,
            "messages": render_messages(step_log.messages),
            "observation": observation,
            "ended": self.session.ended,
            "won": self.session.won,
        }

    def reset(self) -> dict:
        self.emu.load_state()
        self.session = None
        self.terminal_observation = None
        return self.observe()

    # TODO: add apply_team() for team modifications
