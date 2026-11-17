"""Command-line entry point."""

import argparse
from importlib.metadata import version

PROGRAM_NAME = "RepoMentor"


def build_parser() -> argparse.ArgumentParser:
    """Create the parser that reads the command-line arguments."""
    parser = argparse.ArgumentParser(
        prog=PROGRAM_NAME,
        description="Explain a GitHub repository like a senior engineer would on your first day.",
    )
    parser.add_argument(
        "repo",
        help="GitHub repository URL or path to a local folder",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{PROGRAM_NAME} {version(PROGRAM_NAME)}",
    )
    return parser


def main() -> None:
    """Run the RepoMentor command."""
    args = build_parser().parse_args()
    print(f"Analyzing repository: {args.repo}")