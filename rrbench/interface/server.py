import argparse
import json
from pathlib import Path
import socket
import sys

from rrbench.interface.service import BattleService
from rrbench.tasks import load_task


def main() -> None:
    parser = argparse.ArgumentParser(prog="rrbench-env-server")
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--task-dir", type=Path, required=True)
    args = parser.parse_args()

    task = load_task(args.task_dir)
    service = BattleService(task)
    socket_path = args.socket
    bound = False

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        try:
            listener.bind(str(socket_path))
            bound = True
            socket_path.chmod(0o600)
            listener.listen()

            while True:
                connection, address = listener.accept()
                with connection:
                    try:
                        with connection.makefile("rb") as request_file:
                            request_line = request_file.readline()
                        request = json.loads(request_line)

                        if not isinstance(request, dict):
                            result = {"ok": False, "error": "request must be a JSON object"}
                        elif request.get("verb") == "observe":
                            result = service.observe()
                        elif request.get("verb") == "lead":
                            pokemon = request.get("pokemon")
                            if not isinstance(pokemon, str):
                                result = {"ok": False, "error": "lead requires a string pokemon"}
                            else:
                                result = service.lead(pokemon)
                        elif request.get("verb") == "action":
                            command = request.get("command")
                            if not isinstance(command, str):
                                result = {"ok": False, "error": "action requires a string command"}
                            else:
                                result = service.action(command)
                        elif request.get("verb") == "reset":
                            result = service.reset()
                        else:
                            result = {"ok": False, "error": "unknown request verb"}
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
