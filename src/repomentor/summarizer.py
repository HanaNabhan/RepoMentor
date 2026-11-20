"""Ask the AI what each code file does, and then what the whole repository does.

File summaries: files are grouped into batches up to a size budget, so a repository
with 100 code files needs about 10 requests instead of 100. That matters on the
Gemini free tier, which allows only a few requests per day.

Repository summary: one request built from the collected facts and the file
summaries, not from the code again.
"""

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from repomentor.ai_client import AIError, ask_json, number_lines
from repomentor.analysis import FileSummary, KeyFile, RepoAnalysis, RepoSummary
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

MAX_KEY_FILES = 7

REPO_SCHEMA = {
    "type": "object",
    "properties": {
        "purpose": {"type": "string", "description": "2 to 3 sentences: what the project is and who it is for."},
        "how_it_works": {"type": "string", "description": "One short paragraph: the main parts and how they connect."},
        "key_files": {
            "type": "array",
            "description": f"3 to {MAX_KEY_FILES} files a new developer should read first, most important first.",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "A file path exactly as listed."},
                    "why": {"type": "string", "description": "One sentence: why to read this file."},
                },
                "required": ["path", "why"],
            },
        },
    },
    "required": ["purpose", "how_it_works", "key_files"],
}


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


def summarize_repository(analysis: RepoAnalysis) -> RepoSummary | None:
    """Explain the whole repository from the facts and file summaries. Returns None if the AI fails."""
    try:
        answer = ask_json(build_repo_prompt(analysis), REPO_SCHEMA, INSTRUCTIONS)
    except AIError as error:
        print(f"AI step stopped: {error}")
        print("Finished steps are cached. Run the same command again to continue.")
        return None

    purpose = str(answer.get("purpose", "")).strip()
    how_it_works = str(answer.get("how_it_works", "")).strip()
    if not purpose or not how_it_works:
        print("AI step stopped: Gemini returned an empty repository summary.")
        return None

    # Keep only key files that really exist, each listed once.
    existing_paths = {file.path for file in analysis.files}
    key_files: list[KeyFile] = []
    for item in answer.get("key_files", []):
        path, why = item.get("path"), str(item.get("why", "")).strip()
        if path in existing_paths and why and path not in {key.path for key in key_files}:
            key_files.append(KeyFile(path, why))

    return RepoSummary(purpose, how_it_works, key_files[:MAX_KEY_FILES])


def build_repo_prompt(analysis: RepoAnalysis) -> str:
    """Write the request from verified facts: languages, frameworks, structure and file summaries."""
    languages = ", ".join(f"{total.language} ({total.lines:,} lines)" for total in analysis.languages[:6])
    frameworks = ", ".join(f"{framework.name} ({framework.category})" for framework in analysis.frameworks)

    top_level = Counter(
        file.path.split("/")[0] + ("/" if "/" in file.path else "") for file in analysis.files
    )
    structure = ", ".join(f"{entry} ({count} files)" for entry, count in sorted(top_level.items()))

    summaries = "\n".join(
        f"- {path} [{summary.role}]: {summary.summary}" for path, summary in analysis.file_summaries.items()
    )

    task = (
        "Explain this repository to a new developer: its purpose, how it works, and which files to read first. "
        "Choose key files only from the file summaries below, using their paths exactly as written."
    )
    return "\n\n".join([
        f"Repository: {analysis.name}",
        task,
        f"Languages: {languages or 'none'}",
        f"Frameworks and tools: {frameworks or 'none detected'}",
        f"Top-level structure: {structure}",
        f"File summaries:\n{summaries}",
    ])