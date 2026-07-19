import json
from pathlib import Path
import stat
import subprocess
import sys

import pytest

from rrbench.harness.coding_agent import get_agent
from rrbench.harness.runner import COMPLETION_GRACE_SECONDS, Runner, main


def test_prepare_workspace_exposes_only_public_material(tmp_path: Path) -> None:
    runner = Runner(
        task_dir=Path("tasks/giovanni"),
        max_episodes=2,
        image="python:3.12-slim",
        server_image="rrbench-server:dev",
        timeout_seconds=30,
        keep=False,
    )

    workspace, scratch, trajectory_path, score_path = runner.prepare_workspace(tmp_path)

    assert {path.name for path in workspace.iterdir()} == {
        "ENV_USAGE.md",
        "data",
        "scratch",
        "bin",
    }
    assert scratch == workspace / "scratch"
    assert trajectory_path == tmp_path / "harness" / "trajectory.jsonl"
    assert score_path == tmp_path / "harness" / "score.json"
    usage = (workspace / "ENV_USAGE.md").read_text()
    assert "no_battle" in usage
    assert "in_battle" in usage
    assert "ended" in usage
    assert "do not change game state" in usage
    assert "An episode is one attempt" in usage
    assert "even if you reset before the current battle ends" in usage
    assert "species_id" in usage
    assert "apply-team" in usage
    assert "rrbench-env team" in usage
    assert "abilities.json" in usage
    assert "This task permits team modifications" in usage
    assert "This task permits EV updates" in usage
    assert {path.name for path in (workspace / "data").iterdir()} == {
        "abilities.json",
        "moves.json",
        "species.json",
    }
    abilities = json.loads((workspace / "data" / "abilities.json").read_text())
    assert abilities[66] == {
        "name": "Blaze",
        "description": "Boosts Fire moves by 50% at 1/3 or less HP.",
    }
    species = json.loads((workspace / "data" / "species.json").read_text())
    assert species[1] == {
        "name": "Bulbasaur",
        "types": ["Grass", "Poison"],
        "base_stats": {
            "hp": 45,
            "atk": 49,
            "def": 49,
            "spe": 45,
            "spa": 65,
            "spdef": 65,
        },
        "abilities": {"normal": [65], "hidden": 34},
    }


def test_recording_mounts_trial_video_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = Runner(
        task_dir=Path("tasks/giovanni"),
        max_episodes=2,
        image="python:3.12-slim",
        server_image="rrbench-server:dev",
        timeout_seconds=30,
        keep=False,
        record=True,
    )
    commands = []

    def run_command(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("rrbench.harness.runner.subprocess.run", run_command)
    runner.start_server(
        tmp_path,
        "trial-network",
        "trial-server",
        tmp_path / "harness" / "trajectory.jsonl",
        tmp_path / "harness" / "score.json",
    )

    command = commands[0]
    assert (tmp_path / "videos").is_dir()
    assert f"type=bind,src={tmp_path / 'videos'},dst=/videos" in command
    assert command[-1:] == ["--record"]


def test_agent_mode_requires_trusted_runtime_configuration(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="credential_dir is required"):
        Runner(
            task_dir=Path("tasks/giovanni"),
            max_episodes=2,
            image=None,
            server_image="rrbench-server:dev",
            timeout_seconds=30,
            keep=False,
            agent=get_agent("codex"),
            model="gpt-5",
            egress_network="provider-egress",
            egress_proxy="http://provider-proxy:3128",
        )

    with pytest.raises(ValueError, match="egress_network is required"):
        Runner(
            task_dir=Path("tasks/giovanni"),
            max_episodes=2,
            image=None,
            server_image="rrbench-server:dev",
            timeout_seconds=30,
            keep=False,
            agent=get_agent("codex"),
            model="gpt-5",
            credential_dir=tmp_path,
            egress_proxy="http://provider-proxy:3128",
        )


def test_agent_and_manual_command_are_mutually_exclusive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "rrbench-runner",
            "tasks/giovanni",
            "--agent",
            "codex",
            "--command",
            "true",
        ],
    )

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 2


def test_auth_setup_makes_credential_directory_private(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credential_dir = tmp_path / "credentials"
    credential_dir.mkdir(mode=0o755)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "rrbench-runner",
            "--agent",
            "codex",
            "--auth-setup",
            "--credential-dir",
            str(credential_dir),
            "--egress-network",
            "rrbench-egress",
            "--egress-proxy",
            "http://provider-proxy:3128",
        ],
    )
    monkeypatch.setattr(Runner, "prepare_agent_image", lambda self: None)
    monkeypatch.setattr(Runner, "validate_egress", lambda self: None)
    monkeypatch.setattr(
        "rrbench.harness.runner.subprocess.run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 0),
    )

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 0
    assert stat.S_IMODE(credential_dir.stat().st_mode) == 0o700


def test_sandbox_stops_agent_after_server_completion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = Runner(
        task_dir=Path("tasks/giovanni"),
        max_episodes=1,
        image="python:3.12-slim",
        server_image="rrbench-server:dev",
        timeout_seconds=60,
        keep=False,
    )
    workspace = tmp_path / "workspace"
    scratch = workspace / "scratch"
    harness = tmp_path / "harness"
    scratch.mkdir(parents=True)
    harness.mkdir()
    (harness / "complete").touch()
    commands = []
    wait_timeouts = []

    class FakeProcess:
        def poll(self):
            return None

        def wait(self, timeout=None):
            if timeout is not None:
                wait_timeouts.append(timeout)
                raise subprocess.TimeoutExpired("docker start", timeout)
            return 143

    def run_command(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="143\n")

    monkeypatch.setattr("rrbench.harness.runner.shutil.which", lambda command: "/usr/bin/docker")
    monkeypatch.setattr("rrbench.harness.runner.subprocess.run", run_command)
    monkeypatch.setattr(
        "rrbench.harness.runner.subprocess.Popen",
        lambda command, **kwargs: FakeProcess(),
    )

    result = runner.start_sandbox(
        workspace,
        scratch,
        "agent-container",
        "trial-network",
        ["true"],
        tmp_path / "stdout.jsonl",
        tmp_path / "stderr.log",
        False,
    )

    assert result == (0, False)
    assert wait_timeouts == [COMPLETION_GRACE_SECONDS]
    assert ["docker", "stop", "--time", "1", "agent-container"] in commands


def test_sandbox_allows_agent_to_finalize_after_server_completion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = Runner(
        task_dir=Path("tasks/giovanni"),
        max_episodes=1,
        image="python:3.12-slim",
        server_image="rrbench-server:dev",
        timeout_seconds=30,
        keep=False,
    )
    workspace = tmp_path / "workspace"
    scratch = workspace / "scratch"
    harness = tmp_path / "harness"
    scratch.mkdir(parents=True)
    harness.mkdir()
    (harness / "complete").touch()
    commands = []

    class FakeProcess:
        def poll(self):
            return None

        def wait(self, timeout=None):
            return 0

    def run_command(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="0\n")

    monkeypatch.setattr("rrbench.harness.runner.shutil.which", lambda command: "/usr/bin/docker")
    monkeypatch.setattr("rrbench.harness.runner.subprocess.run", run_command)
    monkeypatch.setattr(
        "rrbench.harness.runner.subprocess.Popen",
        lambda command, **kwargs: FakeProcess(),
    )

    result = runner.start_sandbox(
        workspace,
        scratch,
        "agent-container",
        "trial-network",
        ["true"],
        tmp_path / "stdout.jsonl",
        tmp_path / "stderr.log",
        False,
    )

    assert result == (0, False)
    assert not any(command[:2] == ["docker", "stop"] for command in commands)


@pytest.mark.parametrize(
    ("return_code", "timed_out", "server_score", "expected_reason"),
    [
        (124, True, None, "agent_timeout"),
        (7, False, None, "agent_nonzero_exit:7"),
        (0, False, "won", "environment_reported_win"),
    ],
)
def test_runner_finalizes_one_score_and_cleans_transient_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    return_code: int,
    timed_out: bool,
    server_score: str | None,
    expected_reason: str,
) -> None:
    credentials = tmp_path / "credentials"
    credentials.mkdir()
    artifacts = tmp_path / "artifacts"
    runner = Runner(
        task_dir=Path("tasks/giovanni"),
        max_episodes=2,
        image="rrbench-codex:test",
        server_image="rrbench-server:dev",
        timeout_seconds=30,
        keep=False,
        agent=get_agent("codex"),
        model="gpt-5",
        credential_dir=credentials,
        egress_network="provider-egress",
        egress_proxy="http://provider-proxy:3128",
        artifacts_dir=artifacts,
    )

    monkeypatch.setattr(runner, "create_network", lambda network_name: None)
    monkeypatch.setattr(
        runner,
        "start_server",
        lambda root, network_name, server_name, trajectory_path, score_path: None,
    )
    monkeypatch.setattr(runner, "wait_for_server", lambda server_name: None)
    monkeypatch.setattr("rrbench.harness.runner.shutil.which", lambda command: None)

    def run_sandbox(
        workspace: Path,
        scratch: Path,
        container_name: str,
        network_name: str,
        command: list[str],
        stdout_path: Path,
        stderr_path: Path,
        interactive: bool,
    ) -> tuple[int, bool]:
        stdout_path.write_text(
            '{"type":"turn.completed","usage":{"input_tokens":3,"output_tokens":2}}\n'
        )
        stderr_path.write_text("diagnostic\n")
        (scratch / "notes.txt").write_text("retained\n")
        harness = workspace.parent / "harness"
        (harness / "trajectory.jsonl").write_text(
            '{"type":"trial","task_id":"giovanni","max_episodes":2}\n'
        )
        if server_score is not None:
            score = {
                "task_id": "giovanni",
                "status": server_score,
                "reason": "environment_reported_win",
                "episodes": 1,
            }
            (harness / "score.json").write_text(json.dumps(score) + "\n")
        return return_code, timed_out

    monkeypatch.setattr(runner, "start_sandbox", run_sandbox)

    result = runner.run(["codex"])

    trial_root = next(artifacts.iterdir())
    score_files = list(trial_root.rglob("score.json"))
    score = json.loads(score_files[0].read_text())
    metadata = json.loads((trial_root / "metadata.json").read_text())
    assert result == return_code
    assert len(score_files) == 1
    assert score["reason"] == expected_reason
    assert metadata["score"] == score
    assert metadata["agent"]["usage"]["input_tokens"] == 3
    assert (trial_root / "agent-stream.jsonl").exists()
    assert (trial_root / "agent-stderr.log").read_text() == "diagnostic\n"
    assert (trial_root / "agent-scratch" / "notes.txt").read_text() == "retained\n"
    assert not (trial_root / "workspace").exists()
