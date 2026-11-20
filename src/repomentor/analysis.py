"""Collect everything RepoMentor knows about a repository into one record, and save it as JSON.
"""

import json
from dataclasses import asdict, dataclass, field
from importlib.metadata import version
from pathlib import Path

from repomentor.detector import DetectionResult, Framework
from repomentor.scanner import FileInfo, ScanResult
from repomentor.summarizer import FileSummary


@dataclass
class LanguageTotal:
    """File and line counts for one language."""

    language: str
    files: int
    lines: int


@dataclass
class RepoAnalysis:
    """All facts collected about a repository."""

    repomentor_version: str
    name: str
    source: str
    total_files: int
    total_lines: int
    skipped_files: int
    languages: list[LanguageTotal]
    frameworks: list[Framework]
    unparsed_files: list[str]
    files: list[FileInfo]
    file_summaries: dict[str, FileSummary] = field(default_factory=dict)


def build_analysis(repo: str, repo_path: Path, scan: ScanResult, detection: DetectionResult) -> RepoAnalysis:
    """Combine the scan and detection results into one record."""
    source = repo if repo.startswith("https://") else str(repo_path)
    return RepoAnalysis(
        repomentor_version=version("RepoMentor"),
        name=repo_path.name,
        source=source,
        total_files=len(scan.files),
        total_lines=sum(file.lines for file in scan.files),
        skipped_files=scan.skipped,
        languages=[LanguageTotal(*total) for total in scan.language_totals()],
        frameworks=detection.frameworks,
        unparsed_files=detection.unparsed_files,
        files=scan.files,
    )


def save_analysis(analysis: RepoAnalysis, path: Path) -> None:
    """Write the analysis as readable JSON. The same repository always gives the same file."""
    text = json.dumps(asdict(analysis), indent=2, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8")