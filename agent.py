from abc import ABC, abstractmethod

from battle import AttemptRecord, BattleState, StepLog
from context import build_action_context, build_lead_context, build_replacement_context


class Agent(ABC):

    def __init__(self, team: str, max_attempts: int) -> None:
        self.team = team
        self.max_attempts = max_attempts
        self.prior_attempts: list[AttemptRecord] = []

    @abstractmethod
    def pick_lead(self) -> str:
        """Iteration 0 — returns name of the Pokemon to lead with."""

    @abstractmethod
    def step(self, state: BattleState, history: list[StepLog]) -> str:
        """
        Iteration 1+ — returns one action string for battle.py:
          FIGHT <move>    — normal move
          SWITCH <name>   — voluntary switch
          SEND <name>     — forced replacement (wraps agent's name-only output)
        """


class HardcodedAgent(Agent):
    """
    Leads Incineroar and steps through a fixed move list for integration testing.
    Pokemon transitions happen via forced replacement after faints (SEND_ORDER determines sequence).
    Plan entries are skipped if the active Pokemon doesn't know the move.
    """

    LEAD = "Incineroar"

    PLAN = [
        # Incineroar
        "FIGHT Fake Out",
        "FIGHT Taunt",
        "FIGHT Flare Blitz",
        "FIGHT Darkest Lariat",
        # Gyarados (sent in after Incineroar faints)
        "FIGHT Ice Fang",
        "FIGHT Aqua Tail",
        "FIGHT Crunch",
        "FIGHT Aqua Tail",
        # Kingambit
        "FIGHT Kowtow Cleave",
        "FIGHT Iron Head",
        "FIGHT Sucker Punch",
        # Mawile
        "FIGHT Play Rough",
        "FIGHT Iron Head",
        # Tsareena
        "FIGHT Power Whip",
        "FIGHT High Jump Kick",
        # Armarouge
        "FIGHT Armor Cannon",
        "FIGHT Psychic",
    ]

    SEND_ORDER = ["Gyarados", "Kingambit", "Mawile", "Tsareena", "Armarouge", "Incineroar"]

    def __init__(self, team: str, max_attempts: int = 5) -> None:
        super().__init__(team, max_attempts)
        self.plan_idx = 0
        self.log_entries: list[str] = []

    def log(self, header: str, context: str, output: str) -> None:
        self.log_entries.append(
            f"### {header}\n\n**Input context:**\n\n```\n{context}\n```\n\n**Output:** `{output}`"
        )

    def pick_lead(self) -> str:
        self.plan_idx = 0
        attempt_num = len(self.prior_attempts) + 1
        context = build_lead_context(self.team, self.prior_attempts)
        self.log(f"Attempt {attempt_num}, Iteration 0 — pick_lead", context, self.LEAD)
        return self.LEAD

    def step(self, state: BattleState, history: list[StepLog]) -> str:
        turn = len(history) + 1
        attempt_num = len(self.prior_attempts) + 1

        if state.needs_replacement:
            context = build_replacement_context(state, history, self.team, self.prior_attempts)
            alive = {p.name for p in state.party if p.current_hp > 0}
            name = next((n for n in self.SEND_ORDER if n in alive), None)
            if name is None:
                raise RuntimeError("All Pokemon have fainted — battle should have ended already")
            self.log(f"Attempt {attempt_num}, Iteration {turn} — pick_replacement (Turn {turn})", context, name)
            return f"SEND {name}"

        context = build_action_context(state, history, self.team, self.prior_attempts)
        active = state.party[state.active_slot]
        action = None
        while self.plan_idx < len(self.PLAN):
            candidate = self.PLAN[self.plan_idx]
            self.plan_idx += 1
            if candidate[6:] in active.moves:  # strip "FIGHT "
                action = candidate
                break
        if action is None:
            action = next((f"FIGHT {m}" for m in active.moves if m), None)
            if action is None:
                raise RuntimeError(f"{active.name} has no usable moves")

        self.log(f"Attempt {attempt_num}, Iteration {turn} — step (Turn {turn})", context, action)
        return action

    def write_log(self, path: str) -> None:
        with open(path, "w") as f:
            f.write("# Battle Log\n\n" + "\n\n---\n\n".join(self.log_entries) + "\n")
