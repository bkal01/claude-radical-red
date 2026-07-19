import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

from rrbench.harness.coding_agent import (
    AGENTS,
    AgentLimits,
    CodingAgentAdapter,
    build_prompt,
    get_agent,
)
from rrbench.tasks import TeamModification, load_task

COMPLETION_GRACE_SECONDS = 30


class AuthenticationRequiredError(RuntimeError):
    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        super().__init__(f"authentication_required: run authentication setup for {agent_id}")


class Runner:
    def __init__(
        self,
        task_dir: Path,
        max_episodes: int,
        image: str | None,
        server_image: str,
        timeout_seconds: int,
        keep: bool,
        agent: CodingAgentAdapter | None = None,
        model: str | None = None,
        agent_turn_limit: int | None = None,
        reasoning_effort: str | None = None,
        credential_dir: Path | None = None,
        egress_network: str | None = None,
        egress_proxy: str | None = None,
        artifacts_dir: Path | None = None,
        record: bool = False,
        pids_limit: int = 256,
        memory: str = "2g",
        cpus: float = 2.0,
    ) -> None:
        if max_episodes < 1:
            raise ValueError("max_episodes must be at least 1")
        if timeout_seconds < 1:
            raise ValueError("timeout_seconds must be at least 1")
        if agent_turn_limit is not None and agent_turn_limit < 1:
            raise ValueError("agent_turn_limit must be at least 1")
        if pids_limit < 1:
            raise ValueError("pids_limit must be at least 1")
        if cpus <= 0:
            raise ValueError("cpus must be greater than 0")
        if agent is not None and not model:
            raise ValueError("model is required with agent mode")
        if agent is not None and credential_dir is None:
            raise ValueError("credential_dir is required with agent mode")
        if agent is not None and not egress_network:
            raise ValueError("egress_network is required with agent mode")
        if agent is not None and not egress_proxy:
            raise ValueError("egress_proxy is required with agent mode")

        self.task_dir = task_dir.resolve()
        self.max_episodes = max_episodes
        self.agent = agent
        self.agent_version = agent.version if agent else None
        self.model = model
        self.agent_turn_limit = agent_turn_limit
        self.reasoning_effort = reasoning_effort
        self.image = image or (agent.default_image if agent else "python:3.12-slim")
        self.server_image = server_image
        self.timeout_seconds = timeout_seconds
        self.keep = keep
        self.credential_dir = credential_dir.resolve() if credential_dir else None
        self.egress_network = egress_network
        self.egress_proxy = egress_proxy
        self.artifacts_dir = artifacts_dir.resolve() if artifacts_dir else None
        self.record = record
        self.pids_limit = pids_limit
        self.memory = memory
        self.cpus = cpus

    def run_shell(self) -> int:
        return self.run(["/bin/sh"], interactive=True)

    def run_agent(self) -> int:
        if self.agent is None or self.model is None or self.credential_dir is None:
            raise ValueError("agent, model, and credential_dir are required")

        task = load_task(self.task_dir)
        prompt = build_prompt(task.id, self.max_episodes)
        limits = AgentLimits(self.agent_turn_limit, self.reasoning_effort)
        command = self.agent.build_command(prompt, self.model, limits)
        self.prepare_agent_image()
        self.validate_egress()
        if not self.authentication_ready():
            raise AuthenticationRequiredError(self.agent.id)
        return self.run(command)

    def run(self, command: list[str], interactive: bool = False) -> int:
        preserve = self.keep or self.agent is not None
        if self.artifacts_dir is not None:
            self.artifacts_dir.mkdir(parents=True, exist_ok=True)
            root = Path(tempfile.mkdtemp(prefix="rrbench-trial-", dir=self.artifacts_dir))
        elif self.agent is not None:
            default_artifacts = Path.cwd() / "logs" / "coding-agent-trials"
            default_artifacts.mkdir(parents=True, exist_ok=True)
            root = Path(tempfile.mkdtemp(prefix="rrbench-trial-", dir=default_artifacts))
        else:
            root = Path(tempfile.mkdtemp(prefix="rrbench-trial-"))

        trial_id = root.name.removeprefix("rrbench-trial-")
        container_name = f"rrbench-{trial_id}"
        server_name = f"{container_name}-env"
        network_name = f"{container_name}-network"
        stdout_path = root / "agent-stream.jsonl"
        stderr_path = root / "agent-stderr.log"
        server_log_path = root / "server.log"
        metadata_path = root / "metadata.json"
        started_at = datetime.now(timezone.utc)
        started = time.monotonic()
        return_code = 1
        timed_out = False
        parsed_output = None
        execution_error = None
        workspace = root / "workspace"
        scratch = workspace / "scratch"
        trajectory_path = root / "harness" / "trajectory.jsonl"
        score_path = root / "harness" / "score.json"

        try:
            try:
                workspace, scratch, trajectory_path, score_path = self.prepare_workspace(root)
                self.create_network(network_name)
                self.start_server(
                    root,
                    network_name,
                    server_name,
                    trajectory_path,
                    score_path,
                )
                self.wait_for_server(server_name)
                return_code, timed_out = self.start_sandbox(
                    workspace,
                    scratch,
                    container_name,
                    network_name,
                    command,
                    stdout_path,
                    stderr_path,
                    interactive,
                )
            except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError) as error:
                execution_error = error

            if self.agent is not None and stdout_path.exists():
                parsed_output = self.agent.parse_output(stdout_path.read_text())

            if not score_path.exists():
                task = load_task(self.task_dir)
                episodes = 1
                if trajectory_path.exists():
                    for line in trajectory_path.read_text().splitlines():
                        event = json.loads(line)
                        if isinstance(event.get("episode"), int):
                            episodes = max(episodes, event["episode"])

                if execution_error is not None:
                    reason = f"runner_error:{type(execution_error).__name__}"
                elif timed_out:
                    reason = "agent_timeout"
                elif return_code != 0:
                    reason = f"agent_nonzero_exit:{return_code}"
                elif parsed_output is not None and parsed_output.parse_error is not None:
                    reason = "structured_output_parse_error"
                else:
                    reason = "agent_exited_without_score"
                score = {
                    "task_id": task.id,
                    "status": "no_win",
                    "reason": reason,
                    "episodes": episodes,
                }
                score_path.parent.mkdir(parents=True, exist_ok=True)
                score_path.write_text(json.dumps(score, separators=(",", ":")) + "\n")

            elapsed_seconds = time.monotonic() - started
            score = json.loads(score_path.read_text())
            if execution_error is not None:
                exit_status = "runner_error"
            elif timed_out:
                exit_status = "timeout"
            elif return_code == 0:
                exit_status = "completed"
            else:
                exit_status = "nonzero_exit"

            metadata = {
                "trial_id": trial_id,
                "started_at": started_at.isoformat(),
                "elapsed_seconds": elapsed_seconds,
                "timeout_seconds": self.timeout_seconds,
                "exit_status": exit_status,
                "exit_code": return_code,
                "score": score,
            }
            if execution_error is not None:
                metadata["error"] = str(execution_error)
            if self.agent is not None:
                metadata["agent"] = {
                    "id": self.agent.id,
                    "model": self.model,
                    "version": self.agent_version,
                    "image": self.image,
                    "usage": {
                        "input_tokens": parsed_output.usage.input_tokens
                        if parsed_output
                        else 0,
                        "cached_input_tokens": parsed_output.usage.cached_input_tokens
                        if parsed_output
                        else 0,
                        "output_tokens": parsed_output.usage.output_tokens
                        if parsed_output
                        else 0,
                        "turns": parsed_output.usage.turns if parsed_output else 0,
                        "cost_usd": parsed_output.usage.cost_usd if parsed_output else None,
                    },
                    "parse_error": parsed_output.parse_error if parsed_output else None,
                }
            metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")

            print(json.dumps(score, separators=(",", ":")))
            return return_code
        finally:
            if shutil.which("docker"):
                if self.record:
                    subprocess.run(
                        ["docker", "stop", "--time", "5", server_name],
                        check=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                logs = subprocess.run(
                    ["docker", "logs", server_name],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if logs.stdout or logs.stderr:
                    server_log_path.write_text(logs.stdout + logs.stderr)
                for name in (container_name, server_name):
                    subprocess.run(
                        ["docker", "rm", "--force", name],
                        check=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                subprocess.run(
                    ["docker", "network", "rm", network_name],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            workspace_path = root / "workspace"
            scratch_path = workspace_path / "scratch"
            scratch_snapshot = root / "agent-scratch"
            if preserve and scratch_path.exists() and not scratch_snapshot.exists():
                shutil.copytree(scratch_path, scratch_snapshot)
            if workspace_path.exists():
                for path in workspace_path.rglob("*"):
                    if path.is_dir():
                        path.chmod(0o755)
                workspace_path.chmod(0o755)
                shutil.rmtree(workspace_path, ignore_errors=True)
            if preserve:
                print(f"trial artifacts: {root}", file=sys.stderr)
            else:
                shutil.rmtree(root, ignore_errors=True)

    def prepare_workspace(self, root: Path) -> tuple[Path, Path, Path, Path]:
        workspace = root / "workspace"
        scratch = workspace / "scratch"
        bin_dir = workspace / "bin"
        data_dir = workspace / "data"
        harness_dir = root / "harness"
        trajectory_path = harness_dir / "trajectory.jsonl"
        score_path = harness_dir / "score.json"
        scratch.mkdir(parents=True)
        bin_dir.mkdir()
        data_dir.mkdir()
        harness_dir.mkdir()
        scratch.chmod(0o777)

        task = load_task(self.task_dir)
        team_optimization_usage = ""
        if task.allowed_team_modifications:
            team_optimization_usage = (
                "## Team optimization\n\n"
                "This task permits team modifications. Use `rrbench-env apply-team '<JSON>'` "
                "during a live battle to forfeit that attempt, or after a loss. A successful "
                "update automatically resets the environment, advances to the next episode, "
                "and applies the accepted configuration. The command is not available before "
                "a battle starts or after a win. Invalid requests do not change the configuration "
                "or reset the episode.\n\n"
            )
        if TeamModification.EVS in task.allowed_team_modifications:
            team_optimization_usage += (
                "### EV updates\n\n"
                "This task permits EV updates. The JSON object must have a `members` array "
                "containing exactly one entry for each team slot. Entries may be in any order "
                "and each must contain `slot`, `species_id`, and `evs`. `species_id` must match "
                "the active team member at that slot. Each `evs` object must contain exactly "
                "`HP`, `ATK`, `DEF`, `SPE`, `SPA`, and `SPDEF`; values must be integers from 0 "
                "through 252, divisible by four, with at most 508 EVs per Pokemon. Species, "
                "moves, items, abilities, and level cannot be changed.\n\n"
                "Example shape:\n\n"
                "```json\n"
                "{\"members\":[{\"slot\":0,\"species_id\":727,\"evs\":{\"HP\":252,\"ATK\":0,\"DEF\":4,\"SPE\":0,\"SPA\":0,\"SPDEF\":252}}]}\n"
                "```\n\n"
            )

        (workspace / "ENV_USAGE.md").write_text(
            "# Environment protocol\n\n"
            "Each `rrbench-env` invocation sends one JSON request to the persistent "
            "battle service and prints one JSON response. Responses contain `ok: true` "
            "on success. Invalid calls return `ok: false` with an `error` string and do "
            "not change game state.\n\n"
            "## Phases and commands\n\n"
            "- `no_battle`: use `rrbench-env lead <pokemon>` to begin an episode.\n"
            "- `in_battle`: use `rrbench-env action FIGHT <move>`, "
            "`rrbench-env action SWITCH <pokemon>`, or `rrbench-env action SEND "
            "<pokemon>`. `SEND` is legal only when `needs_replacement` is true; the "
            "other battle actions are legal only when it is false.\n"
            "- `ended`: the final action returns `ended: true`, `won`, messages, and a "
            "terminal observation. `rrbench-env observe` returns that same terminal "
            "observation until reset.\n\n"
            "`rrbench-env observe` is legal in every phase and has no side effect. "
            "Calls after trial completion are rejected.\n\n"
            "## Episodes and reset\n\n"
            "An episode is one attempt starting from the original battle state. The "
            "trial begins in episode 1, and `rrbench-env lead <pokemon>` starts its "
            "battle. A successful `rrbench-env reset` ends the current episode, restores "
            "the original battle state, and advances to the next episode. This uses an episode "
            "even if you reset before the current battle ends. A reset is rejected when "
            "no episode remains.\n"
            "\n"
            + team_optimization_usage
            + "\n## Reference data\n\n"
            "The files in `/workspace/data` are JSON arrays indexed by game ID. "
            "An opponent observation's `species_id` is the array index for "
            "`species.json`, whose entries contain the species name, types, and base "
            "stats. For example, if `species_id` is `503`, use `species.json[503]`. "
            "`moves.json` is indexed by move ID and can also be searched by move name.\n"
        )

        roster_source = Path(__file__).resolve().parents[2] / "data" / "teams" / "default.md"
        shutil.copyfile(roster_source, workspace / "roster.md")
        public_data = Path(__file__).resolve().parents[2] / "data"
        for name in ("moves.json", "species.json"):
            shutil.copyfile(public_data / name, data_dir / name)

        client_source = Path(__file__).resolve().parents[1] / "interface" / "cli.py"
        client_path = bin_dir / "rrbench-env"
        shutil.copyfile(client_source, client_path)

        for path in workspace.rglob("*"):
            if path == scratch:
                continue
            if path.is_dir():
                path.chmod(0o555)
            else:
                path.chmod(0o555 if path == client_path else 0o444)
        workspace.chmod(0o555)

        return workspace, scratch, trajectory_path, score_path

    def create_network(self, network_name: str) -> None:
        if not shutil.which("docker"):
            raise RuntimeError("Docker is required to run the agent sandbox")
        subprocess.run(
            ["docker", "network", "create", "--internal", network_name],
            check=True,
            stdout=subprocess.DEVNULL,
        )

    def start_server(
        self,
        root: Path,
        network_name: str,
        server_name: str,
        trajectory_path: Path,
        score_path: Path,
    ) -> None:
        harness_dir = trajectory_path.parent
        command = [
            "docker",
            "run",
            "--detach",
            "--name",
            server_name,
            "--network",
            network_name,
            "--network-alias",
            "rrbench-env",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=256m",
            "--mount",
            f"type=bind,src={self.task_dir},dst=/task,readonly",
            "--mount",
            f"type=bind,src={self.task_dir.parents[1] / 'radicalred.gba'},dst=/app/radicalred.gba,readonly",
            "--mount",
            f"type=bind,src={harness_dir},dst=/trial",
        ]
        if self.record:
            record_dir = root / "videos"
            record_dir.mkdir(exist_ok=True)
            command.extend(
                [
                    "--mount",
                    f"type=bind,src={record_dir},dst=/videos",
                ]
            )
        command.extend(
            [
                self.server_image,
                "python",
                "-m",
                "rrbench.interface.server",
                "--port",
                "8000",
                "--task-dir",
                "/task",
                "--max-episodes",
                str(self.max_episodes),
                "--trajectory-path",
                str(Path("/trial") / trajectory_path.name),
                "--score-path",
                str(Path("/trial") / score_path.name),
            ]
        )
        if self.record:
            command.append("--record")
        subprocess.run(
            command,
            check=True,
            stdout=subprocess.DEVNULL,
        )

    def wait_for_server(self, server_name: str) -> None:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            result = subprocess.run(
                [
                    "docker",
                    "exec",
                    server_name,
                    "python",
                    "-c",
                    "import socket; socket.create_connection(('127.0.0.1', 8000), 0.1).close()",
                ],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if result.returncode == 0:
                return
            time.sleep(0.05)
        logs = subprocess.run(
            ["docker", "logs", server_name],
            check=False,
            capture_output=True,
            text=True,
        )
        raise RuntimeError(f"environment server did not start: {logs.stderr.strip()}")

    def start_sandbox(
        self,
        workspace: Path,
        scratch: Path,
        container_name: str,
        network_name: str,
        command: list[str],
        stdout_path: Path,
        stderr_path: Path,
        interactive: bool,
    ) -> tuple[int, bool]:
        if not shutil.which("docker"):
            raise RuntimeError("Docker is required to run the agent sandbox")

        docker_command = [
            "docker",
            "create",
            "--name",
            container_name,
            "--init",
            "--read-only",
            "--user",
            "1000:1000",
            "--network",
            network_name,
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--pids-limit",
            str(self.pids_limit),
            "--memory",
            self.memory,
            "--cpus",
            str(self.cpus),
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=256m,uid=1000,gid=1000",
            "--mount",
            f"type=bind,src={workspace},dst=/workspace,readonly",
            "--mount",
            f"type=bind,src={scratch},dst=/workspace/scratch",
            "--workdir",
            "/workspace/scratch",
            "--env",
            f"HOME={self.agent.home if self.agent else '/tmp'}",
            "--env",
            "PATH=/workspace/bin:/usr/local/bin:/usr/bin:/bin",
            "--env",
            "RRBENCH_ENV_HOST=rrbench-env",
            "--env",
            "RRBENCH_ENV_PORT=8000",
        ]
        if self.agent is not None and self.credential_dir is not None:
            docker_command.extend(
                [
                    "--mount",
                    f"type=bind,src={self.credential_dir},dst=/provider-auth-ro,readonly",
                    "--tmpfs",
                    "/provider-auth:rw,noexec,nosuid,size=16m,uid=1000,gid=1000",
                    "--env",
                    f"{self.agent.credential_environment}={self.agent.credential_target}",
                    "--env",
                    f"HTTPS_PROXY={self.egress_proxy}",
                    "--env",
                    f"HTTP_PROXY={self.egress_proxy}",
                    "--env",
                    "NO_PROXY=rrbench-env,localhost,127.0.0.1",
                ]
            )
        if interactive and sys.stdin.isatty():
            docker_command.extend(["--interactive", "--tty"])
        docker_command.append(self.image)
        if self.agent is not None:
            docker_command.extend(
                [
                    "sh",
                    "-c",
                    'cp -R /provider-auth-ro/. /provider-auth/ && exec "$@"',
                    "rrbench-agent",
                    *command,
                ]
            )
        else:
            docker_command.extend(command)
        subprocess.run(docker_command, check=True, stdout=subprocess.DEVNULL)

        if self.agent is not None and self.egress_network is not None:
            subprocess.run(
                ["docker", "network", "connect", self.egress_network, container_name],
                check=True,
                stdout=subprocess.DEVNULL,
            )

        start_command = ["docker", "start", "--attach"]
        if interactive:
            start_command.append("--interactive")
        start_command.append(container_name)

        stdout_file = None
        stderr_file = None
        if not interactive:
            stdout_file = stdout_path.open("w")
            stderr_file = stderr_path.open("w")

        try:
            process = subprocess.Popen(
                start_command,
                stdout=stdout_file,
                stderr=stderr_file,
                text=not interactive,
            )
            completion_path = workspace.parent / "harness" / "complete"
            deadline = time.monotonic() + self.timeout_seconds

            while process.poll() is None:
                if completion_path.exists():
                    grace_seconds = min(
                        COMPLETION_GRACE_SECONDS,
                        max(0, deadline - time.monotonic()),
                    )
                    try:
                        process.wait(timeout=grace_seconds)
                    except subprocess.TimeoutExpired:
                        subprocess.run(
                            ["docker", "stop", "--time", "1", container_name],
                            check=False,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                        process.wait()
                    return 0, False
                if time.monotonic() >= deadline:
                    subprocess.run(
                        ["docker", "kill", container_name],
                        check=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    process.wait()
                    return 124, True
                time.sleep(0.05)
        finally:
            if stdout_file is not None:
                stdout_file.close()
            if stderr_file is not None:
                stderr_file.close()

        if completion_path.exists():
            return 0, False

        inspect = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.ExitCode}}", container_name],
            check=True,
            capture_output=True,
            text=True,
        )
        return int(inspect.stdout.strip()), False

    def prepare_agent_image(self) -> None:
        if self.agent is None:
            return
        if not shutil.which("docker"):
            raise RuntimeError("Docker is required to build the agent image")

        if self.image != self.agent.default_image:
            result = subprocess.run(
                ["docker", "image", "inspect", self.image],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if result.returncode != 0:
                raise RuntimeError(f"agent image does not exist: {self.image}")
        else:
            repository = Path(__file__).resolve().parents[2]
            subprocess.run(
                [
                    "docker",
                    "build",
                    "--file",
                    str(repository / self.agent.dockerfile),
                    "--tag",
                    self.agent.default_image,
                    str(repository),
                ],
                check=True,
            )

        version = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--read-only",
                "--user",
                "1000:1000",
                "--network",
                "none",
                self.image,
                *self.agent.version_command(),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        self.agent_version = version.stdout.strip()

    def authentication_ready(self) -> bool:
        if self.agent is None or self.credential_dir is None:
            return False
        if not self.credential_dir.is_dir():
            return False

        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--read-only",
                "--user",
                "1000:1000",
                "--network",
                "none",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=64m,uid=1000,gid=1000",
                "--mount",
                f"type=bind,src={self.credential_dir},dst=/provider-auth-ro,readonly",
                "--tmpfs",
                "/provider-auth:rw,noexec,nosuid,size=16m,uid=1000,gid=1000",
                "--env",
                f"HOME={self.agent.home}",
                "--env",
                f"{self.agent.credential_environment}={self.agent.credential_target}",
                self.image,
                "sh",
                "-c",
                'cp -R /provider-auth-ro/. /provider-auth/ && exec "$@"',
                "rrbench-auth-check",
                *self.agent.authentication_check_command(),
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return result.returncode == 0

    def validate_egress(self) -> None:
        if self.egress_network is None:
            raise ValueError("egress_network is required")
        result = subprocess.run(
            [
                "docker",
                "network",
                "inspect",
                "--format",
                "{{.Internal}}",
                self.egress_network,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise ValueError(f"egress network does not exist: {self.egress_network}")
        if result.stdout.strip() != "true":
            raise ValueError("egress network must be internal and use an allowlisted proxy")


def main() -> None:
    parser = argparse.ArgumentParser(prog="rrbench-runner")
    parser.add_argument("task_dir", type=Path, nargs="?")
    launch_mode = parser.add_mutually_exclusive_group()
    launch_mode.add_argument("--agent", choices=sorted(AGENTS))
    launch_mode.add_argument("--command", nargs=argparse.REMAINDER)
    parser.add_argument("--model")
    parser.add_argument("--max-episodes", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--image")
    parser.add_argument("--server-image", default="rrbench-server:dev")
    parser.add_argument("--agent-turn-limit", type=int)
    parser.add_argument("--reasoning-effort", choices=("low", "medium", "high"))
    parser.add_argument(
        "--credential-dir",
        type=Path,
        help="dedicated provider state directory outside the task workspace",
    )
    parser.add_argument(
        "--egress-network",
        help="trusted internal Docker network containing the allowlisted proxy",
    )
    parser.add_argument(
        "--egress-proxy",
        help="proxy URL reachable only through the trusted egress network",
    )
    parser.add_argument("--artifacts-dir", type=Path)
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--pids-limit", type=int, default=256)
    parser.add_argument("--memory", default="2g")
    parser.add_argument("--cpus", type=float, default=2.0)
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--auth-setup", action="store_true")
    args = parser.parse_args()

    try:
        if args.auth_setup:
            if not args.agent:
                raise ValueError("--auth-setup requires --agent")
            if args.task_dir is not None:
                raise ValueError("TASK_DIR is not used with --auth-setup")
            if args.credential_dir is None or not args.egress_network or not args.egress_proxy:
                raise ValueError(
                    "--auth-setup requires --credential-dir, --egress-network, and "
                    "--egress-proxy"
                )
            adapter = get_agent(args.agent)
            credential_dir = args.credential_dir.resolve()
            credential_dir.mkdir(parents=True, exist_ok=True)
            credential_dir.chmod(0o700)
            image = args.image or adapter.default_image
            setup_runner = Runner(
                task_dir=Path("."),
                max_episodes=1,
                image=image,
                server_image=args.server_image,
                timeout_seconds=args.timeout_seconds,
                keep=False,
            )
            setup_runner.agent = adapter
            setup_runner.egress_network = args.egress_network
            setup_runner.prepare_agent_image()
            setup_runner.validate_egress()
            setup_command = [
                "docker",
                "run",
                "--rm",
                "--interactive",
                "--tty",
                "--read-only",
                "--user",
                "1000:1000",
                "--network",
                args.egress_network,
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=64m,uid=1000,gid=1000",
                "--mount",
                f"type=bind,src={credential_dir},dst={adapter.credential_target}",
                "--env",
                f"HOME={adapter.home}",
                "--env",
                f"{adapter.credential_environment}={adapter.credential_target}",
                "--env",
                f"HTTPS_PROXY={args.egress_proxy}",
                "--env",
                f"HTTP_PROXY={args.egress_proxy}",
                image,
                *adapter.authentication_command(),
            ]
            raise SystemExit(subprocess.run(setup_command, check=False).returncode)

        if args.task_dir is None:
            raise ValueError("TASK_DIR is required")
        adapter = get_agent(args.agent) if args.agent else None
        runner = Runner(
            task_dir=args.task_dir,
            max_episodes=args.max_episodes,
            image=args.image,
            server_image=args.server_image,
            timeout_seconds=args.timeout_seconds,
            keep=args.keep,
            agent=adapter,
            model=args.model,
            agent_turn_limit=args.agent_turn_limit,
            reasoning_effort=args.reasoning_effort,
            credential_dir=args.credential_dir,
            egress_network=args.egress_network,
            egress_proxy=args.egress_proxy,
            artifacts_dir=args.artifacts_dir,
            record=args.record,
            pids_limit=args.pids_limit,
            memory=args.memory,
            cpus=args.cpus,
        )
        if adapter is not None:
            raise SystemExit(runner.run_agent())
        if args.command:
            raise SystemExit(runner.run(args.command))
        raise SystemExit(runner.run_shell())
    except AuthenticationRequiredError as error:
        setup_message = (
            f"run rrbench-runner --agent {error.agent_id} --auth-setup with the same "
            "--credential-dir, --egress-network, and --egress-proxy"
        )
        print(
            json.dumps(
                {
                    "status": "authentication_required",
                    "agent": error.agent_id,
                    "message": setup_message,
                },
                separators=(",", ":"),
            )
        )
        raise SystemExit(2)
    except (RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"rrbench-runner failed: {error}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
