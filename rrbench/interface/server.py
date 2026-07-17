import argparse
import json
from pathlib import Path
import signal
import socket
import sys

from rrbench.harness.recording import TrialRecorder
from rrbench.harness.trial import Trial
from rrbench.interface.service import BattleService
from rrbench.tasks import load_task


def stop_server(signal_number, frame) -> None:
    raise KeyboardInterrupt


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
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args()

    task = load_task(args.task_dir)
    service = BattleService(task)
    trial = Trial(
        task=task,
        max_episodes=args.max_episodes,
        trajectory_path=args.trajectory_path,
        score_path=args.score_path,
    )
    recorder = TrialRecorder(Path("/videos")) if args.record else None
    completion_path = args.score_path.with_name("complete")
    socket_path = args.socket
    bound = False
    signal.signal(signal.SIGTERM, stop_server)

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
                    recording_started = False
                    try:
                        with connection.makefile("rb") as request_file:
                            request_line = request_file.readline()
                        request = json.loads(request_line)
                        verb = request.get("verb")
                        if recorder is not None and verb == "lead":
                            recording_started = recorder.start(service.emu)
                        elif recorder is not None and verb == "reset":
                            recorder.close(service.emu)

                        result = trial.handle(request, service)
                        if recorder is not None and verb == "reset" and result["ok"]:
                            recorder.next_episode()
                        if recorder is not None and verb == "action" and result.get("ended"):
                            recorder.close(service.emu)
                        if recorder is not None and recording_started and not result["ok"]:
                            recorder.discard(service.emu)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        result = {"ok": False, "error": "request must be valid JSON"}
                    except Exception as error:
                        if recorder is not None and recording_started:
                            recorder.discard(service.emu)
                        print(f"rrbench-env-server request failed: {error}", file=sys.stderr)
                        result = {"ok": False, "error": "server failed to process request"}

                    try:
                        connection.sendall(json.dumps(result, separators=(",", ":")).encode() + b"\n")
                    except OSError:
                        pass
                    if trial.finished:
                        completion_path.touch()
                        break
        except KeyboardInterrupt:
            pass
        finally:
            if recorder is not None:
                recorder.close(service.emu)
            if bound and socket_path:
                socket_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
