"""Command-line entry point for RepoMentor."""

import argparse
import sys
from importlib.metadata import version

from repomentor.detector import DetectionResult, detect_frameworks
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


def print_frameworks(detection: DetectionResult) -> None:
    """Print the detected frameworks, where each was found, and any warnings."""
    print()
    if not detection.frameworks:
        print("No known frameworks detected")
    else:
        print(f"{'Category':<18}{'Framework':<16}{'Found in'}")
        for framework in detection.frameworks:
            location = framework.file if framework.line is None else f"{framework.file} line {framework.line}"
            print(f"{framework.category:<18}{framework.name:<16}{location}")

    undeclared = detection.undeclared()
    if undeclared:
        names = ", ".join(framework.name for framework in undeclared)
        print(f"Imported but not declared in any dependency file: {names}")

    if detection.unparsed_files:
        names = ", ".join(detection.unparsed_files)
        print(f"Could not parse {len(detection.unparsed_files)} file(s), skipped for detection: {names}")


def main() -> None:
    """Run the RepoMentor command."""
    args = build_parser().parse_args()

    try:
        repo_path = get_repository(args.repo)
    except FetchError as error:
        sys.exit(f"{PROGRAM_NAME}: error: {error}")

    print(f"Repository ready: {repo_path}")
    scan = scan_repository(repo_path)
    print_summary(scan)
    print_frameworks(detect_frameworks(repo_path, scan))