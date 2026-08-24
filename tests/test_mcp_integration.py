import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import pytest


def extract_result(result):
    if isinstance(result, dict):
        return result
    data = getattr(result, "data", None)
    if isinstance(data, dict):
        return data
    structured_content = getattr(result, "structured_content", None)
    if isinstance(structured_content, dict):
        return structured_content
    for content in getattr(result, "content", []):
        if getattr(content, "type", None) == "text":
            data = json.loads(content.text)
            if isinstance(data, dict):
                return data
    raise AssertionError(f"MCP tool returned no JSON result: {result!r}")


@pytest.mark.integration
def test_mcp_server_exposes_public_battle_contract(tmp_path) -> None:
    pytest.importorskip("fastmcp", reason="fastmcp is required for the MCP integration test")
    pytest.importorskip("mgba.core", reason="mGBA Python bindings are required for the MCP integration test")

    repository = Path(__file__).resolve().parents[1]
    task_directory = repository / "tasks" / "giovanni-silph-co-easy"
    rom_path = repository / "radicalred.gba"
    save_state_path = task_directory / "save_state.ss0"
    if not rom_path.is_file() or not save_state_path.is_file():
        pytest.skip("the integration test requires radicalred.gba and the Giovanni save state")

    with socket.socket() as port_socket:
        port_socket.bind(("127.0.0.1", 0))
        port = port_socket.getsockname()[1]

    environment = os.environ.copy()
    environment.update(
        {
            "RRBENCH_TASK_DIR": str(task_directory),
            "RRBENCH_RECORD": "false",
            "RRBENCH_MAX_EPISODES": "1",
            "RRBENCH_PORT": str(port),
            "RRBENCH_TRAJECTORY_PATH": str(tmp_path / "trajectory.jsonl"),
            "RRBENCH_SCORE_PATH": str(tmp_path / "score.json"),
            "RRBENCH_VIDEO_DIR": str(tmp_path / "videos"),
        }
    )
    server_process = subprocess.Popen(
        [sys.executable, "-m", "rrbench.interface.mcp_server"],
        cwd=repository,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    server_output = ""
    failure = None

    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if server_process.poll() is not None:
                raise RuntimeError("MCP server exited before becoming ready")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("MCP server did not become ready within 20 seconds")

        async def exercise_client():
            from fastmcp import Client
            from fastmcp.client.transports import StreamableHttpTransport

            transport = StreamableHttpTransport(f"http://127.0.0.1:{port}/mcp")
            async with Client(transport) as client:
                tools = await client.list_tools()
                tool_names = {tool.name for tool in tools}
                assert {
                    "observe",
                    "team",
                    "lead",
                    "action",
                    "apply_team",
                    "reset",
                } <= tool_names

                raw_observe_result = await client.call_tool("observe")
                assert raw_observe_result.structured_content is None
                assert len(raw_observe_result.content) == 1
                observe_result = extract_result(raw_observe_result)
                assert observe_result["ok"] is True
                observation = observe_result["observation"]
                assert observation["phase"] == "awaiting_team"

                members = [
                    {
                        "slot": slot,
                        "species_id": 94,
                        "level": 57,
                        "nature_id": 0,
                        "ability_id": 26,
                        "move_ids": [325, 95, 122, 180],
                        "held_item_id": 0,
                        "evs": {
                            "HP": 0,
                            "ATK": 0,
                            "DEF": 0,
                            "SPE": 0,
                            "SPA": 0,
                            "SPDEF": 0,
                        },
                    }
                    for slot in range(6)
                ]
                apply_team_result = extract_result(
                    await client.call_tool("apply_team", {"team": {"members": members}})
                )
                assert apply_team_result["ok"] is True

                observe_result = extract_result(await client.call_tool("observe"))
                team_result = extract_result(await client.call_tool("team"))
                assert observe_result["ok"] is True
                observation = observe_result["observation"]
                assert observation["phase"] == "no_battle"
                assert observation["party"]
                assert all(member["name"] and "moves" in member for member in observation["party"])
                assert team_result["ok"] is True
                team_members = team_result["team"]["members"]
                assert team_members
                assert all(
                    {"slot", "species_id", "name", "moves", "evs", "stats"} <= set(member)
                    for member in team_members
                )

                team_names = {member["name"] for member in team_members}
                lead_name = next(
                    member["name"]
                    for member in observation["party"]
                    if member["name"] in team_names
                )
                lead_result = extract_result(
                    await client.call_tool("lead", {"pokemon": lead_name})
                )
                assert lead_result["ok"] is True
                assert isinstance(lead_result["messages"], list)
                assert isinstance(lead_result["observation"], dict)
                assert isinstance(lead_result["ended"], bool)
                assert isinstance(lead_result["won"], bool)

                if not lead_result["ended"]:
                    battle_observation = lead_result["observation"]
                    assert battle_observation["phase"] == "in_battle"
                    assert battle_observation["needs_replacement"] is False
                    active = battle_observation["party"][battle_observation["active"]["slot"]]
                    move = next(
                        move
                        for move in active["moves"]
                        if move["pp_remaining"] > 0
                    )
                    action_result = extract_result(
                        await client.call_tool(
                            "action",
                            {"command": f"FIGHT {move['name']}"},
                        )
                    )
                    assert action_result["ok"] is True
                    assert isinstance(action_result["messages"], list)
                    assert isinstance(action_result["observation"], dict)
                    assert isinstance(action_result["ended"], bool)
                    assert isinstance(action_result["won"], bool)
                    if action_result["ended"]:
                        assert action_result["observation"]["phase"] == "ended"
                    else:
                        assert action_result["observation"]["phase"] == "in_battle"

        asyncio.run(exercise_client())
    except Exception as error:
        failure = error
    finally:
        if server_process.poll() is None:
            server_process.terminate()
            try:
                server_output = server_process.communicate(timeout=5)[0]
            except subprocess.TimeoutExpired:
                server_process.kill()
                server_output = server_process.communicate()[0]
        else:
            server_output = server_process.communicate()[0]

    if failure is not None:
        pytest.fail(f"MCP integration failed: {failure}\nServer diagnostics:\n{server_output}")
