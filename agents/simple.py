import argparse
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from agent import Agent
from battle import BattleState, StepLog
from context import (
    build_action_context,
    build_lead_context,
    build_replacement_context,
    build_propose_team_context,
)
from team import PokemonConfig, TeamConfig

load_dotenv()


_SYSTEM_PROMPT = (
    "You are a Pokemon battler whose goal is to win the battle against an enemy trainer. "
    "The enemy AI is deterministic: given the exact same game state, it always takes "
    "the same action, and the same attacks crit, miss, and deal the same damage. As long "
    "as you replay the same sequence of actions, the battle unfolds identically. "
    "Write your answer exactly as instructed by the user."
)

_PROPOSE_SYSTEM_PROMPT = (
    "You are a Pokemon battler whose goal is to win the battle against an enemy trainer. "
    "You are reviewing the history of failed attempts to optimize your team's EV "
    "allocations for a better chance of winning on your next try. "
    "The enemy AI is deterministic: given the exact same game state, it always takes "
    "the same action, and the same attacks crit, miss, and deal the same damage. As long "
    "as you replay the same sequence of actions, the battle unfolds identically. "
    "Write your EV allocations exactly as instructed by the user."
)

_EV_LINE_RE = re.compile(
    r'^.*?:\s*HP\s*(\d+)\s*,\s*ATK\s*(\d+)\s*,\s*DEF\s*(\d+)\s*,'
    r'\s*SPATK\s*(\d+)\s*,\s*SPDEF\s*(\d+)\s*,\s*SPD\s*(\d+)',
    re.IGNORECASE,
)


class SimpleAgent(Agent):
    """
    At each iteration:
    - construct the relevant context (team, turn history in this episode,
        episode history, known info about enemy team, etc.)
    - make a single call to an LLM with the entire context and receive a single action back
    """

    def __init__(
        self,
        team: str,
        max_episodes: int,
        model_name: str = "gpt-5-mini",
        debug: bool = False,
    ):
        super().__init__(team, max_episodes)
        self.model_name = model_name
        self.debug = debug
        self._log_path = f"logs/battle_{self.run_id}.md"
        Path("logs").mkdir(exist_ok=True)
        Path(self._log_path).write_text("# Battle Log\n\n")

        self.client = OpenAI(
            api_key=os.environ.get("LLM_API_KEY"),
            base_url=os.environ.get("LLM_BASE_URL"),
        )
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_reasoning_tokens = 0

    @classmethod
    def from_args(cls, team: str, args: argparse.Namespace) -> "SimpleAgent":
        return cls(team, max_episodes=args.max_episodes, model_name=args.model,
                   debug=getattr(args, "debug", False))

    def call_llm(self, context: str) -> tuple[str, str | None, int, int, int]:
        response = self.client.responses.create(
            model=self.model_name,
            reasoning={"effort": "medium", "summary": "auto"},
            instructions=_SYSTEM_PROMPT,
            input=context,
        )
        action = response.output_text.strip()
        reasoning = None
        for item in response.output:
            if item.type == "reasoning" and item.summary:
                reasoning = " ".join(s.text for s in item.summary if hasattr(s, "text"))
                break

        usage = response.usage
        input_tokens = usage.input_tokens if usage else 0
        output_tokens = usage.output_tokens if usage else 0
        reasoning_tokens = (
            getattr(usage.output_tokens_details, "reasoning_tokens", 0)
            if usage and usage.output_tokens_details
            else 0
        )
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_reasoning_tokens += reasoning_tokens

        return action, reasoning, input_tokens, output_tokens, reasoning_tokens

    def log_episode_start(self) -> None:
        episode = len(self.prior_episodes) + 1
        with open(self._log_path, "a") as f:
            f.write(f"## Episode {episode}\n\n")
            f.write(self.team + "\n\n")

    def _write_full_io(self, label: str, system_prompt: str, context: str,
                       reasoning: str | None, output: str,
                       input_tokens: int, output_tokens: int, reasoning_tokens: int) -> None:
        """Debug mode: append the exact LLM input and output verbatim to the log."""
        block = [
            f"### {label} (debug: full I/O)",
            "",
            "**SYSTEM PROMPT:**", "```", system_prompt, "```",
            "**INPUT PROMPT:**", "```", context, "```",
            "**OUTPUT — reasoning:**", "```", reasoning or "(none)", "```",
            "**OUTPUT — response:**", "```", output, "```",
            f"**Tokens:** {input_tokens} in / {output_tokens} out ({reasoning_tokens} reasoning)",
            "",
        ]
        with open(self._log_path, "a") as f:
            f.write("\n".join(block) + "\n")

    def log_step(
        self,
        state: BattleState | None,
        action: str,
        reasoning: str | None,
        input_tokens: int,
        output_tokens: int,
        reasoning_tokens: int,
        context: str | None = None,
        system_prompt: str | None = None,
    ) -> None:
        episode = len(self.prior_episodes) + 1
        if state is None:
            label = f"Episode {episode} | lead"
        elif state.needs_replacement:
            label = f"Episode {episode} | replacement"
        else:
            label = f"Episode {episode} | action"

        reasoning_str = f'"{reasoning}"' if reasoning else "(no reasoning)"
        print(f"[{label}] → {action}  |  {reasoning_str}  |  {input_tokens} in / {output_tokens} out ({reasoning_tokens} reasoning)")

        if self.debug and context is not None:
            self._write_full_io(label, system_prompt or "", context, reasoning, action,
                                input_tokens, output_tokens, reasoning_tokens)
            return

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
        lines.append(f"**Tokens:** {input_tokens} in / {output_tokens} out ({reasoning_tokens} reasoning)")
        lines.append("")
        with open(self._log_path, "a") as f:
            f.write("\n".join(lines) + "\n")

    def log_propose_team(
        self,
        current_config: TeamConfig,
        new_config: TeamConfig,
        reasoning: str | None,
        input_tokens: int,
        output_tokens: int,
        reasoning_tokens: int,
        context: str | None = None,
        system_prompt: str | None = None,
        raw_output: str | None = None,
    ) -> None:
        episode_num = len(self.prior_episodes)
        label = f"Episode {episode_num} | propose_team"

        reasoning_str = f'"{reasoning}"' if reasoning else "(no reasoning)"
        print(f"[{label}]  |  {reasoning_str}  |  {input_tokens} in / {output_tokens} out ({reasoning_tokens} reasoning)")

        if self.debug and context is not None:
            self._write_full_io(label, system_prompt or "", context, reasoning, raw_output or "",
                                input_tokens, output_tokens, reasoning_tokens)
            return

        pokemon_names = [line[3:].strip() for line in self.team.split('\n') if line.startswith('## ')]

        def fmt_evs(evs: dict) -> str:
            return (
                f"HP {evs.get('HP', 0)} | ATK {evs.get('ATK', 0)} | DEF {evs.get('DEF', 0)} | "
                f"SPATK {evs.get('SPA', 0)} | SPDEF {evs.get('SPDEF', 0)} | SPD {evs.get('SPE', 0)}"
            )

        lines = [f"### {label}"]
        if reasoning:
            lines.append(f"**Reasoning:** {reasoning}")
        lines.append("")
        for name, old, new in zip(pokemon_names, current_config.members, new_config.members):
            lines.append(f"**{name}**")
            lines.append(f"  Current:  {fmt_evs(old.evs)}")
            lines.append(f"  Proposed: {fmt_evs(new.evs)}")
        lines.append("")
        lines.append(f"**Tokens:** {input_tokens} in / {output_tokens} out ({reasoning_tokens} reasoning)")
        lines.append("")
        with open(self._log_path, "a") as f:
            f.write("\n".join(lines) + "\n")

    def pick_lead(self) -> str:
        self.log_episode_start()
        context = build_lead_context(self.team, self.prior_episodes)
        action, reasoning, in_tok, out_tok, r_tok = self.call_llm(context)
        self.log_step(None, action, reasoning, in_tok, out_tok, r_tok,
                      context=context, system_prompt=_SYSTEM_PROMPT)
        return action

    def step(self, state: BattleState, history: list[StepLog]) -> str:
        if state.needs_replacement:
            context = build_replacement_context(state, history, self.team, self.prior_episodes)
        else:
            context = build_action_context(state, history, self.team, self.prior_episodes)
        action, reasoning, in_tok, out_tok, r_tok = self.call_llm(context)
        self.log_step(state, action, reasoning, in_tok, out_tok, r_tok,
                      context=context, system_prompt=_SYSTEM_PROMPT)
        return f"SEND {action}" if state.needs_replacement else action

    def propose_team(self, current_config: TeamConfig) -> TeamConfig | None:
        context = build_propose_team_context(self.team, self.prior_episodes)

        response = self.client.responses.create(
            model=self.model_name,
            reasoning={"effort": "medium", "summary": "auto"},
            instructions=_PROPOSE_SYSTEM_PROMPT,
            input=context,
        )
        raw = response.output_text.strip()
        reasoning = None
        for item in response.output:
            if item.type == "reasoning" and item.summary:
                reasoning = " ".join(s.text for s in item.summary if hasattr(s, "text"))
                break
        usage = response.usage
        in_tok = usage.input_tokens if usage else 0
        out_tok = usage.output_tokens if usage else 0
        r_tok = (
            getattr(usage.output_tokens_details, "reasoning_tokens", 0)
            if usage and usage.output_tokens_details
            else 0
        )
        self.total_input_tokens += in_tok
        self.total_output_tokens += out_tok
        self.total_reasoning_tokens += r_tok

        lines = [l.strip() for l in raw.splitlines() if l.strip()]
        matches = [m for line in lines if (m := _EV_LINE_RE.match(line))]
        episode_num = len(self.prior_episodes)

        if len(matches) != len(current_config.members):
            print(f"[Episode {episode_num} | propose_team] parse failed: expected {len(current_config.members)} EV lines, got {len(matches)}")
            if self.debug:
                self._write_full_io(f"Episode {episode_num} | propose_team (parse failed)",
                                    _PROPOSE_SYSTEM_PROMPT, context, reasoning, raw,
                                    in_tok, out_tok, r_tok)
            return None

        new_members = []
        for match, member in zip(matches, current_config.members):
            hp, atk, def_, spatk, spdef, spd = (int(g) for g in match.groups())
            new_members.append(PokemonConfig(
                species_id=member.species_id,
                evs={"HP": hp, "ATK": atk, "DEF": def_, "SPA": spatk, "SPDEF": spdef, "SPE": spd},
            ))

        new_config = TeamConfig(members=new_members)
        self.log_propose_team(current_config, new_config, reasoning, in_tok, out_tok, r_tok,
                              context=context, system_prompt=_PROPOSE_SYSTEM_PROMPT, raw_output=raw)
        return new_config
