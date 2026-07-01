import argparse

from agent import Agent
from battle import BattleState, StepLog
from context import build_action_context, build_lead_context, build_replacement_context


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

    def __init__(self, team: str, max_episodes: int = 5) -> None:
        super().__init__(team, max_episodes)
        self.plan_idx = 0
        self.log_entries: list[str] = []

    @classmethod
    def from_args(cls, team: str, args: argparse.Namespace) -> "HardcodedAgent":
        return cls(team, max_episodes=args.max_episodes)

    def log(self, header: str, context: str, output: str) -> None:
        self.log_entries.append(
            f"### {header}\n\n**Input context:**\n\n```\n{context}\n```\n\n**Output:** `{output}`"
        )

    def pick_lead(self) -> str:
        self.plan_idx = 0
        episode_num = len(self.prior_episodes) + 1
        context = build_lead_context(self.team, self.prior_episodes)
        self.log(f"Episode {episode_num}, Iteration 0 — pick_lead", context, self.LEAD)
        return self.LEAD

    def step(self, state: BattleState, history: list[StepLog]) -> str:
        turn = len(history) + 1
        episode_num = len(self.prior_episodes) + 1

        if state.needs_replacement:
            context = build_replacement_context(state, history, self.team, self.prior_episodes)
            alive = {p.name for p in state.party if p.current_hp > 0}
            name = next((n for n in self.SEND_ORDER if n in alive), None)
            if name is None:
                raise RuntimeError("All Pokemon have fainted — battle should have ended already")
            self.log(f"Episode {episode_num}, Iteration {turn} — pick_replacement (Turn {turn})", context, name)
            return f"SEND {name}"

        context = build_action_context(state, history, self.team, self.prior_episodes)
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

        self.log(f"Episode {episode_num}, Iteration {turn} — step (Turn {turn})", context, action)
        return action

    def write_log(self, path: str) -> None:
        with open(path, "w") as f:
            f.write("# Battle Log\n\n" + "\n\n---\n\n".join(self.log_entries) + "\n")
