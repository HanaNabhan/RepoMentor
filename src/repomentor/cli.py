"""Command-line entry point for RepoMentor."""

import argparse
import sys
from importlib.metadata import version
from pathlib import Path

from repomentor.ai_client import usage
from repomentor.analysis import RepoAnalysis, build_analysis, save_analysis
from repomentor.detector import DetectionResult, detect_frameworks
from repomentor.fetcher import FetchError, get_repository
from repomentor.overview import render_files_page, render_overview
from repomentor.scanner import ScanResult, scan_repository
from repomentor.summarizer import summarize_files

PROGRAM_NAME = "RepoMentor"
DEFAULT_OUTPUT_DIR = "repomentor-output"


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
        "--output",
        default=DEFAULT_OUTPUT_DIR,
        help=f"folder to write the results to (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="skip all AI steps and write only the facts",
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


def write_output(analysis: RepoAnalysis, output_dir: Path) -> None:
    """Write analysis.json and index.md into the output folder."""
    output_dir.mkdir(parents=True, exist_ok=True)

    analysis_path = output_dir / "analysis.json"
    save_analysis(analysis, analysis_path)
    print(f"Wrote {analysis_path}")

    index_path = output_dir / "index.md"
    index_path.write_text(render_overview(analysis), encoding="utf-8")
    print(f"Wrote {index_path}")

    files_path = output_dir / "files.md"
    files_path.write_text(render_files_page(analysis), encoding="utf-8")
    print(f"Wrote {files_path}")


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
    detection = detect_frameworks(repo_path, scan)
    print_frameworks(detection)

    analysis = build_analysis(args.repo, repo_path, scan, detection)

    ai_complete = True
    if not args.no_ai:
        print()
        result = summarize_files(analysis.name, repo_path, analysis.files)
        analysis.file_summaries = result.summaries
        ai_complete = result.complete
        print(f"AI: {usage.requests} requests, {usage.cache_hits} from cache")

    print()
    try:
        write_output(analysis, Path(args.output))
    except OSError as error:
        sys.exit(f"{PROGRAM_NAME}: error: could not write output: {error}")

    if not ai_complete:
        sys.exit(1)