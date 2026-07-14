#!/usr/bin/env python3
import argparse
import json
import os
import socket
import sys


def main() -> None:
    parser = argparse.ArgumentParser(prog="rrbench-env")
    parser.add_argument("--socket", default=os.environ.get("RRBENCH_ENV_SOCKET"))
    parser.add_argument("--host", default=os.environ.get("RRBENCH_ENV_HOST"))
    parser.add_argument("--port", type=int, default=os.environ.get("RRBENCH_ENV_PORT"))

    subparsers = parser.add_subparsers(dest="verb", required=True)
    subparsers.add_parser("observe")

    lead = subparsers.add_parser("lead")
    lead.add_argument("pokemon")

    action = subparsers.add_parser("action")
    action.add_argument("command", nargs=argparse.REMAINDER)

    subparsers.add_parser("reset")

    args = parser.parse_args()
    if args.socket and (args.host or args.port):
        print("rrbench-env accepts either a socket or host and port", file=sys.stderr)
        raise SystemExit(2)
    if not args.socket and not (args.host and args.port):
        print("rrbench-env requires a socket or host and port", file=sys.stderr)
        raise SystemExit(2)

    request = {"verb": args.verb}
    if args.verb == "lead":
        request["pokemon"] = args.pokemon
    elif args.verb == "action":
        request["command"] = " ".join(args.command)

    try:
        if args.socket:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.connect(args.socket)
        else:
            client = socket.create_connection((args.host, args.port))
        with client:
            client.sendall(json.dumps(request, separators=(",", ":")).encode() + b"\n")
            with client.makefile("rb") as responsefile:
                response = json.loads(responsefile.readline())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        print(f"rrbench-env failed: {error}", file=sys.stderr)
        raise SystemExit(1)

    print(json.dumps(response, separators=(",", ":")))


if __name__ == "__main__":
    main()
