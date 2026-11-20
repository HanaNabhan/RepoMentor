"""Build the overview page (index.md) from a repository analysis. Facts only, no AI."""

from collections import defaultdict

from repomentor.analysis import RepoAnalysis
from repomentor.detector import Framework
from repomentor.scanner import is_code_language
from repomentor.summarizer import ROLE_TITLES


def render_overview(analysis: RepoAnalysis) -> str:
    """Return the full Markdown text of the overview page."""
    sections = [
        render_title(analysis),
        render_repo_summary(analysis),
        render_at_a_glance(analysis),
        render_languages(analysis),
        render_frameworks(analysis),
        render_things_to_check(analysis),
        render_structure(analysis),
    ]
    return "\n\n".join(section for section in sections if section) + "\n"


def render_title(analysis: RepoAnalysis) -> str:
    """Repository name and where it came from."""
    return f"# {analysis.name}\n\nSource: {analysis.source}"


def render_repo_summary(analysis: RepoAnalysis) -> str:
    """The AI overview: purpose, how it works, and files to read first. Empty when there is no summary."""
    summary = analysis.repo_summary
    if summary is None:
        return ""

    lines = ["## What this repository does", "", summary.purpose, "", "### How it works", "", summary.how_it_works]
    if summary.key_files:
        lines += ["", "### Start here", ""]
        for number, key_file in enumerate(summary.key_files, start=1):
            lines.append(f"{number}. `{key_file.path}`: {key_file.why}")
    return "\n".join(lines)


def render_at_a_glance(analysis: RepoAnalysis) -> str:
    """Key numbers in a short list."""
    return "\n".join([
        "## At a glance",
        "",
        f"- **Files:** {analysis.total_files:,}",
        f"- **Lines:** {analysis.total_lines:,}",
        f"- **Main language:** {main_language(analysis)}",
        "",
        "What each file does: [Files](files.md)",
    ])


def main_language(analysis: RepoAnalysis) -> str:
    """Return the programming language with the most lines, ignoring docs and config files."""
    for total in analysis.languages:
        if is_code_language(total.language):
            return total.language
    return analysis.languages[0].language if analysis.languages else "None"


def render_languages(analysis: RepoAnalysis) -> str:
    """Table of languages with file and line counts."""
    lines = ["## Languages", "", "| Language | Files | Lines |", "|---|---:|---:|"]
    for total in analysis.languages:
        lines.append(f"| {cell(total.language)} | {total.files:,} | {total.lines:,} |")
    return "\n".join(lines)


def render_frameworks(analysis: RepoAnalysis) -> str:
    """Table of detected frameworks and the evidence for each."""
    if not analysis.frameworks:
        return "## Frameworks and tools\n\nNo known frameworks detected."

    lines = ["## Frameworks and tools", "", "| Category | Framework | Found in |", "|---|---|---|"]
    for framework in analysis.frameworks:
        lines.append(f"| {framework.category} | {cell(framework.name)} | {evidence(framework)} |")
    return "\n".join(lines)


def evidence(framework: Framework) -> str:
    """Describe where a framework was found, for example: `app.py` line 3."""
    location = f"`{cell(framework.file)}`"
    return location if framework.line is None else f"{location} line {framework.line}"


def render_things_to_check(analysis: RepoAnalysis) -> str:
    """List problems found so far. Returns an empty string when there is nothing to report."""
    undeclared = [framework for framework in analysis.frameworks if framework.source == "import"]
    if not undeclared and not analysis.unparsed_files:
        return ""

    lines = ["## Things to check", ""]
    for framework in undeclared:
        lines.append(
            f"- **{framework.name}** is imported in {evidence(framework)} but not declared "
            "in any dependency file, so others cannot install it automatically."
        )
    for path in analysis.unparsed_files:
        lines.append(
            f"- `{cell(path)}` could not be parsed: it has a syntax error, "
            "or uses syntax newer than the Python running RepoMentor."
        )
    return "\n".join(lines)


def render_structure(analysis: RepoAnalysis) -> str:
    """Show the top-level folders and files, with file and line counts per folder."""
    file_counts: dict[str, int] = defaultdict(int)
    line_counts: dict[str, int] = defaultdict(int)
    for file in analysis.files:
        top, _, rest = file.path.partition("/")
        entry = f"{top}/" if rest else top
        file_counts[entry] += 1
        line_counts[entry] += file.lines

    # Folders first, then files, each in alphabetical order.
    entries = sorted(file_counts, key=lambda entry: (not entry.endswith("/"), entry.lower()))
    lines = ["## Project structure", "", "| Path | Files | Lines |", "|---|---:|---:|"]
    for entry in entries:
        lines.append(f"| `{cell(entry)}` | {file_counts[entry]:,} | {line_counts[entry]:,} |")
    return "\n".join(lines)


def cell(text: str) -> str:
    """Escape the | character, which would otherwise break a Markdown table."""
    return text.replace("|", "\\|")


def render_files_page(analysis: RepoAnalysis) -> str:
    """Return the Markdown text of files.md: every file, grouped by role, with its AI summary."""
    lines = ["# Files", ""]
    summarized = len(analysis.file_summaries)
    lines.append(f"{summarized:,} of {analysis.total_files:,} files have an AI summary.")

    for role, title in ROLE_TITLES.items():
        rows = [
            (file, analysis.file_summaries[file.path])
            for file in analysis.files
            if file.path in analysis.file_summaries and analysis.file_summaries[file.path].role == role
        ]
        if not rows:
            continue
        lines += ["", f"## {title}", "", "| File | Lines | What it does |", "|---|---:|---|"]
        for file, summary in rows:
            lines.append(f"| `{cell(file.path)}` | {file.lines:,} | {cell(one_line(summary.summary))} |")

    not_summarized = [file for file in analysis.files if file.path not in analysis.file_summaries]
    if not_summarized:
        note = "Documentation, configuration and data files, plus any code file the AI step did not reach."
        lines += ["", "## Not summarized", "", note, "", "| File | Language | Lines |", "|---|---|---:|"]
        for file in not_summarized:
            lines.append(f"| `{cell(file.path)}` | {file.language} | {file.lines:,} |")

    return "\n".join(lines) + "\n"


def one_line(text: str) -> str:
    """Join a multi-line text into one line, so it fits in a table cell."""
    return " ".join(text.split())