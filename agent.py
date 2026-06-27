from abc import ABC, abstractmethod
from datetime import datetime

from battle import AttemptRecord, BattleState, StepLog


class Agent(ABC):

    def __init__(self, team: str, max_attempts: int) -> None:
        self.team = team
        self.max_attempts = max_attempts
        self.prior_attempts: list[AttemptRecord] = []
        self.run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

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
