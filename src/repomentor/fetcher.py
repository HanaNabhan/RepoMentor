"""Find or download the repository that RepoMentor will analyze."""

import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

CACHE_DIR = Path.home() / ".repomentor" / "repos"


class FetchError(Exception):
    """Raised when the repository cannot be found or downloaded."""


def get_repository(repo: str) -> Path:
    """Return the local folder of the repository, cloning it first if needed."""
    local_path = Path(repo)
    if local_path.is_dir():
        print("Using local folder")
        return local_path.resolve()

    owner, name = parse_github_url(repo)
    target = CACHE_DIR / owner / name

    if target.is_dir():
        print("Using existing clone")
        return target

    clone_repository(f"https://github.com/{owner}/{name}", target)
    return target


def parse_github_url(url: str) -> tuple[str, str]:
    """Split a GitHub URL such as https://github.com/owner/name into (owner, name)."""
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]

    is_github = parsed.scheme == "https" and parsed.netloc.lower() in ("github.com", "www.github.com")
    if not is_github or len(parts) != 2:
        raise FetchError(
            f"not a local folder or a GitHub repository URL: {url}\n"
            "Expected a URL like https://github.com/<owner>/<name>"
        )

    owner, name = parts
    return owner, name.removesuffix(".git")


def clone_repository(url: str, target: Path) -> None:
    """Download the latest version of the repository into the target folder."""
    if shutil.which("git") is None:
        raise FetchError("Git is not installed or not on PATH. Get it from https://git-scm.com/downloads")

    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"Cloning {url}")

    # Never wait for a username or password: fail with an error instead.
    environment = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
    result = subprocess.run(
        ["git", "clone", "--depth", "1", "--quiet", url, str(target)],
        capture_output=True,
        text=True,
        env=environment,
    )

    if result.returncode != 0:
        git_message = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "no details"
        raise FetchError(
            f"could not clone {url}\n"
            "The repository may not exist, may be private, or there is no internet connection.\n"
            f"Git said: {git_message}"
        )