import argparse
import json
from pathlib import Path
import socket
import sys

from rrbench.harness.trial import Trial
from rrbench.interface.service import BattleService
from rrbench.tasks import load_task


def main() -> None:
    parser = argparse.ArgumentParser(prog="rrbench-env-server")
    transport = parser.add_mutually_exclusive_group(required=True)
    transport.add_argument("--socket", type=Path)
    transport.add_argument("--port", type=int)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--task-dir", type=Path, required=True)
    parser.add_argument("--max-episodes", type=int, required=True)
    parser.add_argument("--trajectory-path", type=Path, required=True)
    parser.add_argument("--score-path", type=Path, required=True)
    args = parser.parse_args()

    task = load_task(args.task_dir)
    trial = Trial(
        task=task,
        max_episodes=args.max_episodes,
        trajectory_path=args.trajectory_path,
        score_path=args.score_path,
        service_factory=BattleService,
    )
    socket_path = args.socket
    bound = False

    family = socket.AF_UNIX if socket_path else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as listener:
        try:
            if socket_path:
                listener.bind(str(socket_path))
            else:
                listener.bind((args.host, args.port))
            bound = True
            if socket_path:
                socket_path.chmod(0o600)
            listener.listen()

            while True:
                connection, address = listener.accept()
                with connection:
                    try:
                        with connection.makefile("rb") as request_file:
                            request_line = request_file.readline()
                        request = json.loads(request_line)

                        result = trial.handle(request)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        result = {"ok": False, "error": "request must be valid JSON"}
                    except Exception as error:
                        print(f"rrbench-env-server request failed: {error}", file=sys.stderr)
                        result = {"ok": False, "error": "server failed to process request"}

                    try:
                        connection.sendall(json.dumps(result, separators=(",", ":")).encode() + b"\n")
                    except OSError:
                        pass
        except KeyboardInterrupt:
            pass
        finally:
            if bound:
                socket_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
