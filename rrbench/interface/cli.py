import argparse
import json
import os
import socket
import sys

from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    parser = argparse.ArgumentParser(prog="rrbench-env")
    parser.add_argument("--socket", default=os.environ.get("RRBENCH_ENV_SOCKET"))

    subparsers = parser.add_subparsers(dest="verb", required=True)
    subparsers.add_parser("observe")

    lead = subparsers.add_parser("lead")
    lead.add_argument("pokemon")

    action = subparsers.add_parser("action")
    action.add_argument("command", nargs=argparse.REMAINDER)

    subparsers.add_parser("reset")

    args = parser.parse_args()
    if not args.socket:
        print("rrbench-env requires --socket or RRBENCH_ENV_SOCKET", file=sys.stderr)
        raise SystemExit(2)

    request = {"verb": args.verb}
    if args.verb == "lead":
        request["pokemon"] = args.pokemon
    elif args.verb == "action":
        request["command"] = " ".join(args.command)

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(args.socket)
            client.sendall(json.dumps(request, separators=(",", ":")).encode() + b"\n")
            with client.makefile("rb") as responsefile:
                response = json.loads(responsefile.readline())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        print(f"rrbench-env failed: {error}", file=sys.stderr)
        raise SystemExit(1)

    print(json.dumps(response, separators=(",", ":")))


if __name__ == "__main__":
    main()
