"""Command-line entry point for RepoMentor."""

import argparse
import sys
from importlib.metadata import version

from repomentor.fetcher import FetchError, get_repository
from repomentor.scanner import ScanResult, scan_repository

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


def print_summary(scan: ScanResult) -> None:
    """Print the file count and a table of languages."""
    print(f"Scanned {len(scan.files)} files, skipped {scan.skipped}")
    print(f"{'Language':<20}{'Files':>7}{'Lines':>9}")
    for language, file_count, line_count in scan.language_totals():
        print(f"{language:<20}{file_count:>7}{line_count:>9}")


def main() -> None:
    """Run the RepoMentor command."""
    args = build_parser().parse_args()

    try:
        repo_path = get_repository(args.repo)
    except FetchError as error:
        sys.exit(f"{PROGRAM_NAME}: error: {error}")

    print(f"Repository ready: {repo_path}")
    print_summary(scan_repository(repo_path))