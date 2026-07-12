import argparse

from rrbench.interface import service

def main(args):
    parser = argparse.ArgumentParser(prog="rrbench")
    sub = parser.add_subparsers(dest="verb", required=True)

    sub.add_parser("observe")

    lead = sub.add_parser("lead")
    lead.add_argument("lead-pokemon")

    if args.verb == "observe":
        result = service.observe()
    elif args.verb == "lead":
        pass
    else:
        raise ValueError(f"Unknown verb {args.verb}")

    print(format(result))