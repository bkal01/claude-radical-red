import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time


class Runner:
    def __init__(
        self,
        task_dir: Path,
        max_episodes: int,
        image: str,
        server_image: str,
        timeout_seconds: int,
        keep: bool,
    ) -> None:
        if max_episodes < 1:
            raise ValueError("max_episodes must be at least 1")
        if timeout_seconds < 1:
            raise ValueError("timeout_seconds must be at least 1")

        self.task_dir = task_dir.resolve()
        self.max_episodes = max_episodes
        self.image = image
        self.server_image = server_image
        self.timeout_seconds = timeout_seconds
        self.keep = keep

    def run_shell(self) -> int:
        return self.run(["/bin/sh"], interactive=True)

    def run(self, command: list[str], interactive: bool = False) -> int:
        root = Path(tempfile.mkdtemp(prefix="rrbench-trial-"))
        container_name = f"rrbench-{root.name.removeprefix('rrbench-trial-')}"
        server_name = f"{container_name}-env"
        network_name = f"{container_name}-network"

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
            return_code = self.start_sandbox(
                workspace,
                scratch,
                container_name,
                network_name,
                command,
                interactive,
            )

            if score_path.exists():
                print(score_path.read_text().strip())
            return return_code
        finally:
            if shutil.which("docker"):
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
            if self.keep:
                print(f"trial artifacts: {root}", file=sys.stderr)
            else:
                shutil.rmtree(root, ignore_errors=True)

    def prepare_workspace(self, root: Path) -> tuple[Path, Path, Path, Path]:
        workspace = root / "workspace"
        scratch = workspace / "scratch"
        bin_dir = workspace / "bin"
        trajectory_path = root / "trajectory.jsonl"
        score_path = root / "score.json"

        scratch.mkdir(parents=True)
        bin_dir.mkdir()
        scratch.chmod(0o777)

        (workspace / "TASK.md").write_text(
            "# Radical Red benchmark\n\n"
            "Win the configured battle within the episode budget. "
            "Interact with the game only through `rrbench-env`.\n"
        )
        (workspace / "ENV_USAGE.md").write_text(
            "# Environment commands\n\n"
            "`rrbench-env observe` reads the current public state.\n\n"
            "`rrbench-env lead <pokemon>` starts an episode.\n\n"
            "`rrbench-env action \"FIGHT <move>\"` takes a battle action. "
            "`SWITCH <pokemon>` and `SEND <pokemon>` are also supported.\n\n"
            "`rrbench-env reset` starts the next episode.\n"
        )
        (workspace / "roster.md").write_text(
            "Run `rrbench-env observe` to view the legal roster and current state.\n"
        )

        client_source = Path(__file__).resolve().parents[1] / "interface" / "cli.py"
        client_path = bin_dir / "rrbench-env"
        shutil.copyfile(client_source, client_path)

        for path in (workspace / "TASK.md", workspace / "ENV_USAGE.md", workspace / "roster.md"):
            path.chmod(0o444)
        client_path.chmod(0o555)
        bin_dir.chmod(0o555)
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
        subprocess.run(
            [
                "docker",
                "run",
                "--detach",
                "--rm",
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
                "/tmp",
                "--mount",
                f"type=bind,src={self.task_dir},dst=/task,readonly",
                "--mount",
                f"type=bind,src={self.task_dir.parents[1] / 'radicalred.gba'},dst=/app/radicalred.gba,readonly",
                "--mount",
                f"type=bind,src={root},dst=/trial",
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
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )

    def wait_for_server(self, server_name: str) -> None:
        deadline = time.monotonic() + 5
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
        interactive: bool,
    ) -> int:
        if not shutil.which("docker"):
            raise RuntimeError("Docker is required to run the agent sandbox")

        docker_command = [
            "docker",
            "run",
            "--rm",
            "--name",
            container_name,
            "--read-only",
            "--network",
            network_name,
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--mount",
            f"type=bind,src={workspace},dst=/workspace,readonly",
            "--mount",
            f"type=bind,src={scratch},dst=/workspace/scratch",
            "--workdir",
            "/workspace/scratch",
            "--env",
            "PATH=/workspace/bin:/usr/local/bin:/usr/bin:/bin",
            "--env",
            "RRBENCH_ENV_HOST=rrbench-env",
            "--env",
            "RRBENCH_ENV_PORT=8000",
        ]
        if interactive and sys.stdin.isatty():
            docker_command.extend(["--interactive", "--tty"])
        docker_command.extend([self.image, *command])

        try:
            result = subprocess.run(docker_command, timeout=self.timeout_seconds, check=False)
        except subprocess.TimeoutExpired:
            print("sandbox timed out", file=sys.stderr)
            return 124
        return result.returncode


def main() -> None:
    parser = argparse.ArgumentParser(prog="rrbench-runner")
    parser.add_argument("task_dir", type=Path)
    parser.add_argument("--max-episodes", type=int, default=1)
    parser.add_argument("--image", default="python:3.12-slim")
    parser.add_argument("--server-image", default="rrbench-server:dev")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--command", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    runner = Runner(
        task_dir=args.task_dir,
        max_episodes=args.max_episodes,
        image=args.image,
        server_image=args.server_image,
        timeout_seconds=args.timeout_seconds,
        keep=args.keep,
    )
    command = args.command
    try:
        if command:
            raise SystemExit(runner.run(command))
        raise SystemExit(runner.run_shell())
    except (RuntimeError, ValueError) as error:
        print(f"rrbench-runner failed: {error}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
