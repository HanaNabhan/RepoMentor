"""Scan a repository folder: list useful files with their language and line count."""

import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

MAX_FILE_SIZE_BYTES = 1024 * 1024
BINARY_CHECK_BYTES = 8192

SKIP_DIRS = {
    ".git", ".hg", ".svn",
    ".venv", "venv", "env", "node_modules", "__pycache__",
    "dist", "build", ".idea", ".vscode",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
    "repomentor-output",
}

SKIP_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "poetry.lock", "Pipfile.lock", "uv.lock",
    "Cargo.lock", "Gemfile.lock", "composer.lock",
    ".DS_Store",
}

LANGUAGES_BY_NAME = {
    "Dockerfile": "Dockerfile",
    "Makefile": "Makefile",
    "CMakeLists.txt": "CMake",
}

LANGUAGES_BY_EXTENSION = {
    ".py": "Python", ".pyi": "Python", ".ipynb": "Jupyter Notebook",
    ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".java": "Java", ".kt": "Kotlin", ".scala": "Scala",
    ".go": "Go", ".rs": "Rust", ".swift": "Swift", ".dart": "Dart",
    ".c": "C", ".h": "C", ".cpp": "C++", ".cc": "C++", ".hpp": "C++",
    ".cs": "C#", ".rb": "Ruby", ".php": "PHP", ".lua": "Lua", ".r": "R",
    ".sh": "Shell", ".bash": "Shell", ".ps1": "PowerShell", ".bat": "Batch", ".cmd": "Batch",
    ".sql": "SQL",
    ".html": "HTML", ".css": "CSS", ".scss": "SCSS", ".vue": "Vue",
    ".md": "Markdown", ".rst": "reStructuredText", ".txt": "Text",
    ".json": "JSON", ".yaml": "YAML", ".yml": "YAML", ".toml": "TOML",
    ".ini": "INI", ".cfg": "INI", ".xml": "XML",
}

# Languages that describe documentation, data or configuration rather than program code.
NON_CODE_LANGUAGES = {"Other", "Text", "Markdown", "reStructuredText", "JSON", "YAML", "TOML", "INI", "XML"}


@dataclass
class FileInfo:
    """One useful file in the repository."""

    path: str
    language: str
    lines: int


@dataclass
class ScanResult:
    """All useful files found in the repository, plus how many files were skipped."""

    files: list[FileInfo] = field(default_factory=list)
    skipped: int = 0

    def language_totals(self) -> list[tuple[str, int, int]]:
        """Return (language, file count, line count) per language, most lines first."""
        file_counts = Counter(file.language for file in self.files)
        line_counts = Counter()
        for file in self.files:
            line_counts[file.language] += file.lines

        totals = [(language, file_counts[language], line_counts[language]) for language in file_counts]
        return sorted(totals, key=lambda total: total[2], reverse=True)


def scan_repository(repo_path: Path) -> ScanResult:
    """Walk the repository and collect every useful file, skipping junk."""
    result = ScanResult()

    for current_dir, dir_names, file_names in os.walk(repo_path):
        # Editing dir_names in place tells os.walk not to enter the skipped folders.
        dir_names[:] = sorted(name for name in dir_names if not is_skipped_dir(name))

        for file_name in sorted(file_names):
            file_path = Path(current_dir) / file_name
            if file_name in SKIP_FILES or not is_text_file(file_path):
                result.skipped += 1
                continue

            result.files.append(
                FileInfo(
                    path=file_path.relative_to(repo_path).as_posix(),
                    language=detect_language(file_path),
                    lines=count_lines(file_path),
                )
            )

    return result


def is_code_language(language: str) -> bool:
    """Return True for programming languages, False for docs, data and config formats."""
    return language not in NON_CODE_LANGUAGES


def is_skipped_dir(name: str) -> bool:
    """Return True for folders that never contain useful source code."""
    return name in SKIP_DIRS or name.endswith(".egg-info")


def is_text_file(path: Path) -> bool:
    """Return True if the file is small enough and contains no null bytes (not binary)."""
    try:
        if path.stat().st_size > MAX_FILE_SIZE_BYTES:
            return False
        with open(path, "rb") as file:
            return b"\0" not in file.read(BINARY_CHECK_BYTES)
    except OSError:
        return False


def detect_language(path: Path) -> str:
    """Guess the language from the file name or extension."""
    if path.name in LANGUAGES_BY_NAME:
        return LANGUAGES_BY_NAME[path.name]
    return LANGUAGES_BY_EXTENSION.get(path.suffix.lower(), "Other")


def count_lines(path: Path) -> int:
    """Count the lines in a text file."""
    with open(path, encoding="utf-8", errors="replace") as file:
        return sum(1 for _ in file)