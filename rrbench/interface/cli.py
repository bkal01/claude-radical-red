import argparse

from rrbench.interface import service

def main():
    parser = argparse.ArgumentParser(prog="rrbench")
    sub = parser.add_subparsers(dest="verb", required=True)

    sub.add_parser("observe")

    lead = sub.add_parser("lead")
    lead.add_argument("lead-pokemon")

    args = parser.parse_args()

    if args.verb == "observe":
        result = service.observe()
    elif args.verb == "lead":
        result = service.lead(args.lead_pokemon)
    else:
        raise ValueError(f"Unknown verb {args.verb}")

    print(format(result))