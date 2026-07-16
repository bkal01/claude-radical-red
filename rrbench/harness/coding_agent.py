from abc import ABC, abstractmethod
from dataclasses import dataclass
import json


@dataclass(frozen=True)
class AgentLimits:
    agent_turn_limit: int | None = None
    reasoning_effort: str | None = None


@dataclass(frozen=True)
class AgentUsage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    turns: int = 0
    cost_usd: float | None = None


@dataclass(frozen=True)
class AgentOutput:
    final_text: str | None
    usage: AgentUsage
    parse_error: str | None = None


class CodingAgentAdapter(ABC):
    id: str
    version: str
    default_image: str
    dockerfile: str
    home: str
    credential_environment: str
    credential_target: str

    @abstractmethod
    def build_command(self, prompt: str, model: str, limits: AgentLimits) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def authentication_command(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def version_command(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def authentication_check_command(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def parse_output(self, output: str) -> AgentOutput:
        raise NotImplementedError


class CodexAdapter(CodingAgentAdapter):
    id = "codex"
    version = "0.144.1"
    default_image = "rrbench-codex:0.144.1"
    dockerfile = "docker/codex.Dockerfile"
    home = "/home/node"
    credential_environment = "CODEX_HOME"
    credential_target = "/provider-auth"

    def build_command(self, prompt: str, model: str, limits: AgentLimits) -> list[str]:
        if limits.agent_turn_limit is not None:
            raise ValueError("codex does not support an agent turn limit")

        command = [
            "codex",
            "exec",
            "--dangerously-bypass-approvals-and-sandbox",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--json",
            "--skip-git-repo-check",
            "--model",
            model,
        ]
        if limits.reasoning_effort is not None:
            command.extend(
                ["--config", f'model_reasoning_effort="{limits.reasoning_effort}"']
            )
        command.append(prompt)
        return command

    def authentication_command(self) -> list[str]:
        return ["codex", "login", "--device-auth"]

    def version_command(self) -> list[str]:
        return ["codex", "--version"]

    def authentication_check_command(self) -> list[str]:
        return ["codex", "login", "status"]

    def parse_output(self, output: str) -> AgentOutput:
        final_text = None
        input_tokens = 0
        cached_input_tokens = 0
        output_tokens = 0
        turns = 0

        for line_number, line in enumerate(output.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as error:
                return AgentOutput(
                    final_text,
                    AgentUsage(
                        input_tokens,
                        cached_input_tokens,
                        output_tokens,
                        turns,
                    ),
                    f"invalid JSON on line {line_number}: {error.msg}",
                )

            if event.get("type") == "item.completed":
                item = event.get("item", {})
                if item.get("type") == "agent_message" and isinstance(item.get("text"), str):
                    final_text = item["text"]
            elif event.get("type") == "turn.completed":
                usage = event.get("usage", {})
                input_tokens += int(usage.get("input_tokens", 0))
                cached_input_tokens += int(usage.get("cached_input_tokens", 0))
                output_tokens += int(usage.get("output_tokens", 0))
                turns += 1

        return AgentOutput(
            final_text,
            AgentUsage(input_tokens, cached_input_tokens, output_tokens, turns),
        )


class ClaudeCodeAdapter(CodingAgentAdapter):
    id = "claude-code"
    version = "2.1.202"
    default_image = "rrbench-claude-code:2.1.202"
    dockerfile = "docker/claude-code.Dockerfile"
    home = "/home/node"
    credential_environment = "CLAUDE_CONFIG_DIR"
    credential_target = "/provider-auth"

    def build_command(self, prompt: str, model: str, limits: AgentLimits) -> list[str]:
        command = [
            "claude",
            "--print",
            "--safe-mode",
            "--dangerously-skip-permissions",
            "--no-session-persistence",
            "--output-format",
            "stream-json",
            "--verbose",
        ]
        if limits.agent_turn_limit is not None:
            command.extend(["--max-turns", str(limits.agent_turn_limit)])
        if limits.reasoning_effort is not None:
            command.extend(["--effort", limits.reasoning_effort])
        command.extend(["--model", model, prompt])
        return command

    def authentication_command(self) -> list[str]:
        return ["claude", "auth", "login", "--claudeai"]

    def version_command(self) -> list[str]:
        return ["claude", "--version"]

    def authentication_check_command(self) -> list[str]:
        return ["claude", "auth", "status", "--json"]

    def parse_output(self, output: str) -> AgentOutput:
        final_text = None
        input_tokens = 0
        cached_input_tokens = 0
        output_tokens = 0
        turns = 0
        cost_usd = None

        for line_number, line in enumerate(output.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as error:
                return AgentOutput(
                    final_text,
                    AgentUsage(
                        input_tokens,
                        cached_input_tokens,
                        output_tokens,
                        turns,
                        cost_usd,
                    ),
                    f"invalid JSON on line {line_number}: {error.msg}",
                )

            if event.get("type") != "result":
                continue
            if isinstance(event.get("result"), str):
                final_text = event["result"]
            usage = event.get("usage", {})
            input_tokens = int(usage.get("input_tokens", 0))
            cached_input_tokens = int(
                usage.get("cache_read_input_tokens", usage.get("cached_input_tokens", 0))
            )
            output_tokens = int(usage.get("output_tokens", 0))
            turns = int(event.get("num_turns", 0))
            if event.get("total_cost_usd") is not None:
                cost_usd = float(event["total_cost_usd"])

        return AgentOutput(
            final_text,
            AgentUsage(input_tokens, cached_input_tokens, output_tokens, turns, cost_usd),
        )


AGENTS: dict[str, CodingAgentAdapter] = {
    CodexAdapter.id: CodexAdapter(),
    ClaudeCodeAdapter.id: ClaudeCodeAdapter(),
}


def get_agent(agent_id: str) -> CodingAgentAdapter:
    try:
        return AGENTS[agent_id]
    except KeyError:
        raise ValueError(f"unknown coding agent: {agent_id}") from None


def build_prompt(task_id: str, max_episodes: int) -> str:
    return (
        f"You are playing Pokemon Radical Red benchmark task {task_id!r}. You control "
        "the supplied player team and must defeat the configured opponent within at "
        f"most {max_episodes} episode(s).\n\n"
        "Read /workspace/ENV_USAGE.md and /workspace/roster.md before acting. They "
        "define the legal commands, episode/reset behavior, available reference data, "
        "and your team.\n\n"
        "Use only rrbench-env for game interaction. Choose a lead to start each "
        "episode, then issue legal battle actions until you win or lose. The opponent "
        "AI is deterministic: when the game state and action history are identical, "
        "it makes the same decisions. Use observations from failed episodes to improve "
        "your strategy, and replay useful action sequences exactly when appropriate.\n\n"
        "Keep tools, notes, and learned information in /workspace/scratch so they "
        "persist across resets. Stop after the environment reports a win, the episode "
        "budget is exhausted, or an unrecoverable environment error occurs."
    )
