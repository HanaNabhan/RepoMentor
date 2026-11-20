"""Ask the AI what each code file does, several files per request.

Files are grouped into batches up to a size budget, so a repository with
80 code files needs about a dozen requests instead of 80.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from repomentor.ai_client import AIError, ask_json, number_lines
from repomentor.scanner import FileInfo, is_code_language

BATCH_CHARACTER_BUDGET = 80_000

# The roles the model may choose from, with the section title used on the files page.
ROLE_TITLES = {
    "entry point": "Entry points",
    "core": "Core",
    "model": "Models and data",
    "api": "API",
    "ui": "User interface",
    "utility": "Utilities",
    "config": "Configuration",
    "test": "Tests",
    "script": "Scripts",
    "other": "Other code",
}

INSTRUCTIONS = (
    "You are a senior software engineer explaining a codebase to a new developer on their first day. "
    "Be accurate and concrete. Describe only what the code shows. "
    "Every line of code is prefixed with its line number."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "files": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "The file path exactly as given."},
                    "role": {"type": "string", "enum": list(ROLE_TITLES)},
                    "summary": {"type": "string", "description": "2 to 3 sentences on what the file does."},
                },
                "required": ["path", "role", "summary"],
            },
        },
    },
    "required": ["files"],
}


@dataclass
class FileSummary:
    """What the AI says one file does."""

    role: str
    summary: str


@dataclass
class SummaryResult:
    """All summaries received, and whether every batch finished."""

    summaries: dict[str, FileSummary] = field(default_factory=dict)
    complete: bool = True


def summarize_files(repo_name: str, repo_path: Path, files: list[FileInfo]) -> SummaryResult:
    """Summarize every non-empty code file. If the AI fails, return what was finished so far."""
    code_files = [file for file in files if is_code_language(file.language) and file.lines > 0]
    batches = make_batches(repo_path, code_files)
    result = SummaryResult()

    for number, batch in enumerate(batches, start=1):
        print(f"Summarizing files: batch {number} of {len(batches)}")
        try:
            answer = ask_json(build_prompt(repo_name, batch), SCHEMA, INSTRUCTIONS)
        except AIError as error:
            print(f"AI step stopped: {error}")
            print("Finished batches are cached. Run the same command again to continue.")
            result.complete = False
            break
        result.summaries.update(check_answer(answer, batch))

    return result


def make_batches(repo_path: Path, files: list[FileInfo]) -> list[list[tuple[str, str]]]:
    """Group (path, text) pairs into batches that stay under the character budget.

    A file larger than the budget gets a batch of its own.
    """
    batches: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    current_size = 0

    for file in files:
        text = read_for_ai(repo_path / file.path)
        if current and current_size + len(text) > BATCH_CHARACTER_BUDGET:
            batches.append(current)
            current, current_size = [], 0
        current.append((file.path, text))
        current_size += len(text)

    if current:
        batches.append(current)
    return batches


def read_for_ai(path: Path) -> str:
    """Return the text to send for a file. For notebooks, only the code cells are sent."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix != ".ipynb":
        return text

    try:
        cells = json.loads(text).get("cells", [])
    except json.JSONDecodeError:
        return text
    parts = []
    for number, cell in enumerate(cells, start=1):
        if cell.get("cell_type") == "code":
            source = cell.get("source", "")
            parts.append(f"# --- cell {number} ---\n" + ("".join(source) if isinstance(source, list) else source))
    return "\n".join(parts)


def build_prompt(repo_name: str, batch: list[tuple[str, str]]) -> str:
    """Write the request: the task, then every file with numbered lines."""
    task = (
        f"Summarize each of the {len(batch)} files below. For every file, give its path exactly as written, "
        "its role, and a summary of 2 to 3 sentences."
    )
    parts = [f"Repository: {repo_name}", task]
    for path, text in batch:
        parts.append(f"=== File: {path} ===\n{number_lines(text)}")
    return "\n\n".join(parts)


def check_answer(answer: dict, batch: list[tuple[str, str]]) -> dict[str, FileSummary]:
    """Keep only summaries for files that were actually sent, with a valid role and a non-empty text."""
    sent_paths = {path for path, _ in batch}
    summaries = {}
    for item in answer.get("files", []):
        path, role, summary = item.get("path"), item.get("role"), str(item.get("summary", "")).strip()
        if path in sent_paths and role in ROLE_TITLES and summary:
            summaries[path] = FileSummary(role, summary)
    return summaries