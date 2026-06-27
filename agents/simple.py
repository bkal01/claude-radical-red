import argparse
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from agent import Agent
from battle import BattleState, StepLog
from context import build_action_context, build_lead_context, build_replacement_context

load_dotenv()

_SYSTEM_PROMPT = (
    "You are a Pokemon battle strategist. "
    "On the first line of your response, write 'REASONING: ' followed by one sentence explaining your decision. "
    "On the second line, write your answer exactly as instructed by the user."
)


@dataclass
class _LLMLog:
    attempt: int
    turn: int | None  # None for pick_lead
    kind: str         # "lead", "action", "replacement"
    reasoning: str | None
    action: str


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
        self._entries: list[_LLMLog] = []
        self._run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

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

    def _log(self, entry: _LLMLog) -> None:
        self._entries.append(entry)
        turn_str = f", Turn {entry.turn}" if entry.turn is not None else ""
        label = f"Attempt {entry.attempt}{turn_str} | {entry.kind}"
        reasoning_str = f'"{entry.reasoning}"' if entry.reasoning else "(no reasoning)"
        print(f"[{label}] → {entry.action}  |  {reasoning_str}")

    def pick_lead(self) -> str:
        attempt = len(self.prior_attempts) + 1
        context = build_lead_context(self.team, self.prior_attempts)
        action, reasoning = self.call_llm(context)
        self._log(_LLMLog(attempt=attempt, turn=None, kind="lead", reasoning=reasoning, action=action))
        return action

    def step(self, state: BattleState, history: list[StepLog]) -> str:
        attempt = len(self.prior_attempts) + 1
        turn = len(history) + 1
        if state.needs_replacement:
            kind = "replacement"
            context = build_replacement_context(state, history, self.team, self.prior_attempts)
        else:
            kind = "action"
            context = build_action_context(state, history, self.team, self.prior_attempts)
        action, reasoning = self.call_llm(context)
        self._log(_LLMLog(attempt=attempt, turn=turn, kind=kind, reasoning=reasoning, action=action))
        return f"SEND {action}" if state.needs_replacement else action

    def write_log(self, _path: str = "") -> None:
        Path("logs").mkdir(exist_ok=True)
        log_path = f"logs/battle_{self._run_ts}.md"
        sections = ["# Battle Log\n"]
        for e in self._entries:
            turn_str = f", Turn {e.turn}" if e.turn is not None else ""
            sections.append(f"### Attempt {e.attempt}{turn_str} — {e.kind}")
            if e.reasoning:
                sections.append(f"**Reasoning:** {e.reasoning}")
            sections.append(f"**Action:** `{e.action}`")
            sections.append("")
        Path(log_path).write_text("\n".join(sections))
        print(f"Log written to {log_path}")
