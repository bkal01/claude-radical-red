import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from agent import Agent
from battle import BattleState, StepLog
from context import build_action_context, build_lead_context, build_replacement_context
from party import PartyPokemon

load_dotenv()

_SYSTEM_PROMPT = (
    "You are a Pokemon battle strategist. "
    "On the first line of your response, write 'REASONING: ' followed by one sentence explaining your decision. "
    "On the second line, write your answer exactly as instructed by the user."
)


class SimpleAgent(Agent):
    """
    At each iteration:
    - construct the relevant context (team, turn history in this attempt,
        attempt history, known info about enemy team, etc.)
    - make a single call to an LLM with the entire context and receive a single action back
    """

    def __init__(
        self,
        team: str,
        max_attempts: int,
        model_name: str = "gpt-5-mini",
    ):
        super().__init__(team, max_attempts)
        self.model_name = model_name
        self._log_path = f"logs/battle_{self.run_id}.md"
        Path("logs").mkdir(exist_ok=True)
        Path(self._log_path).write_text("# Battle Log\n\n")

        self.client = OpenAI(
            api_key=os.environ.get("LLM_API_KEY"),
            base_url=os.environ.get("LLM_BASE_URL"),
        )

    @classmethod
    def from_args(cls, team: str, args: argparse.Namespace) -> "SimpleAgent":
        return cls(team, max_attempts=args.max_attempts, model_name=args.model)

    def call_llm(self, context: str) -> tuple[str, str | None]:
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": context},
            ],
        )
        raw = response.choices[0].message.content.strip()
        lines = [l.strip() for l in raw.splitlines() if l.strip()]
        reasoning = None
        for line in lines:
            if line.startswith("REASONING:"):
                reasoning = line[len("REASONING:"):].strip()
                break
        action = lines[-1] if lines else raw
        return action, reasoning

    def log(self, state: BattleState | None, action: str, reasoning: str | None) -> None:
        attempt = len(self.prior_attempts) + 1
        if state is None:
            label = f"Attempt {attempt} | lead"
        elif state.needs_replacement:
            label = f"Attempt {attempt} | replacement"
        else:
            label = f"Attempt {attempt} | action"

        reasoning_str = f'"{reasoning}"' if reasoning else "(no reasoning)"
        print(f"[{label}] → {action}  |  {reasoning_str}")

        lines = [f"### {label}"]
        if state is not None:
            party_strs = []
            for i, p in enumerate(state.party):
                marker = " *(active)*" if i == state.active_slot else ""
                if p.current_hp == 0:
                    party_strs.append(f"~~{p.name}~~ (fainted){marker}")
                else:
                    party_strs.append(f"{p.name} {p.current_hp}/{p.max_hp}{marker}")
            lines.append("**My party:** " + ", ".join(party_strs))

            opp_hp = (
                f"{state.opp_current_hp}/{state.opp_max_hp}"
                if state.opp_current_hp is not None
                else "?/?"
            )
            lines.append(f"**Opp active:** {state.opp_species} {opp_hp} HP")

        if reasoning:
            lines.append(f"**Reasoning:** {reasoning}")
        lines.append(f"**Action:** `{action}`")
        lines.append("")
        with open(self._log_path, "a") as f:
            f.write("\n".join(lines) + "\n")

    def pick_lead(self) -> str:
        context = build_lead_context(self.team, self.prior_attempts)
        action, reasoning = self.call_llm(context)
        self.log(None, action, reasoning)
        return action

    def step(self, state: BattleState, history: list[StepLog]) -> str:
        if state.needs_replacement:
            context = build_replacement_context(state, history, self.team, self.prior_attempts)
        else:
            context = build_action_context(state, history, self.team, self.prior_attempts)
        action, reasoning = self.call_llm(context)
        self.log(state, action, reasoning)
        return f"SEND {action}" if state.needs_replacement else action
