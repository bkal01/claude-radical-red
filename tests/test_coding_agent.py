import pytest

from rrbench.harness.coding_agent import AgentLimits, build_prompt, get_agent


def test_codex_command_uses_noninteractive_json_mode() -> None:
    command = get_agent("codex").build_command(
        "solve the task", "gpt-5", AgentLimits(reasoning_effort="low")
    )

    assert command == [
        "codex",
        "exec",
        "--dangerously-bypass-approvals-and-sandbox",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--json",
        "--skip-git-repo-check",
        "--model",
        "gpt-5",
        "--config",
        'model_reasoning_effort="low"',
        "solve the task",
    ]


def test_claude_command_uses_noninteractive_stream_mode() -> None:
    command = get_agent("claude-code").build_command(
        "solve the task",
        "sonnet",
        AgentLimits(agent_turn_limit=20, reasoning_effort="low"),
    )

    assert command == [
        "claude",
        "--print",
        "--safe-mode",
        "--dangerously-skip-permissions",
        "--no-session-persistence",
        "--output-format",
        "stream-json",
        "--verbose",
        "--max-turns",
        "20",
        "--effort",
        "low",
        "--model",
        "sonnet",
        "solve the task",
    ]


def test_codex_output_parser_reads_final_text_and_usage() -> None:
    output = "\n".join(
        [
            '{"type":"item.completed","item":{"type":"agent_message","text":"done"}}',
            '{"type":"turn.completed","usage":{"input_tokens":12,'
            '"cached_input_tokens":5,"output_tokens":7}}',
        ]
    )

    result = get_agent("codex").parse_output(output)

    assert result.final_text == "done"
    assert result.usage.input_tokens == 12
    assert result.usage.cached_input_tokens == 5
    assert result.usage.output_tokens == 7
    assert result.usage.turns == 1
    assert result.parse_error is None


def test_claude_output_parser_reads_result_and_usage() -> None:
    output = (
        '{"type":"result","result":"done","num_turns":3,"total_cost_usd":0.25,'
        '"usage":{"input_tokens":12,"cache_read_input_tokens":5,"output_tokens":7}}'
    )

    result = get_agent("claude-code").parse_output(output)

    assert result.final_text == "done"
    assert result.usage.input_tokens == 12
    assert result.usage.cached_input_tokens == 5
    assert result.usage.output_tokens == 7
    assert result.usage.turns == 3
    assert result.usage.cost_usd == 0.25
    assert result.parse_error is None


def test_output_parser_reports_malformed_json() -> None:
    result = get_agent("codex").parse_output("not json")

    assert result.parse_error == "invalid JSON on line 1: Expecting value"


def test_codex_rejects_unsupported_agent_turn_limit() -> None:
    with pytest.raises(ValueError, match="does not support an agent turn limit"):
        get_agent("codex").build_command("solve", "gpt-5", AgentLimits(agent_turn_limit=2))


def test_agent_prompt_has_game_boundary_and_stop_condition() -> None:
    prompt = build_prompt("giovanni", 3)

    assert "rrbench-env" in prompt
    assert "at most 3 episode(s)" in prompt
    assert "Pokemon Radical Red" in prompt
    assert "AI is deterministic" in prompt
    assert "Stop after the environment reports a win" in prompt
    assert "harness score" not in prompt


def test_unknown_agent_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown coding agent"):
        get_agent("other")
