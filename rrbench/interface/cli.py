import argparse

from rrbench.interface import service

def main(args):
    parser = argparse.ArgumentParser(prog="rrbench")
    sub = parser.add_subparsers(dest="verb", required=True)

    sub.add_parser("observe")

    if args.verb == "observe":
        result = service.observe()
    else:
        raise ValueError(f"Unknown verb {args.verb}")

    print(format(result))