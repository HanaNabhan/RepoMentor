"""Detect the frameworks and tools a repository uses.
1. Dependency files (requirements*.txt, pyproject.toml, package.json): what the project declares.
2. Python imports (.py files and Jupyter notebooks): what the code actually uses.
"""

import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import tomli

from repomentor.scanner import ScanResult

SOURCE_DEPENDENCY = "dependency file"
SOURCE_IMPORT = "import"
SOURCE_CONFIG = "config file"

PACKAGE_NAME_PATTERN = re.compile(r"[A-Za-z0-9@][A-Za-z0-9._/@-]*")


@dataclass(frozen=True)
class KnownFramework:
    """A framework RepoMentor can recognize, with its package and import names."""

    name: str
    category: str
    packages: tuple[str, ...]
    imports: tuple[str, ...] = ()


KNOWN_FRAMEWORKS = (
    KnownFramework("Django", "Web", ("django",), ("django",)),
    KnownFramework("Flask", "Web", ("flask",), ("flask",)),
    KnownFramework("FastAPI", "Web", ("fastapi",), ("fastapi",)),
    KnownFramework("Streamlit", "Web", ("streamlit",), ("streamlit",)),
    KnownFramework("Express", "Web", ("express",)),
    KnownFramework("Next.js", "Web", ("next",)),
    KnownFramework("NestJS", "Web", ("@nestjs/core",)),
    KnownFramework("React", "Frontend", ("react",)),
    KnownFramework("Vue", "Frontend", ("vue",)),
    KnownFramework("Angular", "Frontend", ("@angular/core",)),
    KnownFramework("Svelte", "Frontend", ("svelte",)),
    KnownFramework("Vite", "Frontend", ("vite",)),
    KnownFramework("PyTorch", "Machine learning", ("torch",), ("torch",)),
    KnownFramework("TensorFlow", "Machine learning", ("tensorflow",), ("tensorflow",)),
    KnownFramework("Keras", "Machine learning", ("keras",), ("keras",)),
    KnownFramework("scikit-learn", "Machine learning", ("scikit-learn",), ("sklearn",)),
    KnownFramework("Transformers", "Machine learning", ("transformers",), ("transformers",)),
    KnownFramework("XGBoost", "Machine learning", ("xgboost",), ("xgboost",)),
    KnownFramework("OpenCV", "Computer vision", ("opencv-python", "opencv-python-headless"), ("cv2",)),
    KnownFramework("Pillow", "Computer vision", ("pillow",), ("PIL",)),
    KnownFramework("pandas", "Data", ("pandas",), ("pandas",)),
    KnownFramework("NumPy", "Data", ("numpy",), ("numpy",)),
    KnownFramework("SciPy", "Data", ("scipy",), ("scipy",)),
    KnownFramework("Matplotlib", "Data", ("matplotlib",), ("matplotlib",)),
    KnownFramework("Seaborn", "Data", ("seaborn",), ("seaborn",)),
    KnownFramework("SQLAlchemy", "Database", ("sqlalchemy",), ("sqlalchemy",)),
    KnownFramework("SQLModel", "Database", ("sqlmodel",), ("sqlmodel",)),
    KnownFramework("Prisma", "Database", ("prisma", "@prisma/client")),
    KnownFramework("Mongoose", "Database", ("mongoose",)),
    KnownFramework("pytest", "Testing", ("pytest",), ("pytest",)),
    KnownFramework("Jest", "Testing", ("jest",)),
    KnownFramework("Vitest", "Testing", ("vitest",)),
    KnownFramework("Playwright", "Testing", ("playwright", "@playwright/test"), ("playwright",)),
    KnownFramework("Click", "CLI", ("click",), ("click",)),
    KnownFramework("Typer", "CLI", ("typer",), ("typer",)),
    KnownFramework("Jinja", "Library", ("jinja2",), ("jinja2",)),
    KnownFramework("Werkzeug", "Library", ("werkzeug",), ("werkzeug",)),
    KnownFramework("Requests", "Library", ("requests",), ("requests",)),
    KnownFramework("Pydantic", "Library", ("pydantic",), ("pydantic",)),
    KnownFramework("Beautiful Soup", "Library", ("beautifulsoup4",), ("bs4",)),
    KnownFramework("MkDocs", "Tooling", ("mkdocs",), ("mkdocs",)),
)

CONFIG_FILE_FRAMEWORKS = {
    "Dockerfile": KnownFramework("Docker", "Tooling", ()),
    "docker-compose.yml": KnownFramework("Docker", "Tooling", ()),
    "docker-compose.yaml": KnownFramework("Docker", "Tooling", ()),
    "compose.yaml": KnownFramework("Docker", "Tooling", ()),
    "mkdocs.yml": KnownFramework("MkDocs", "Tooling", ()),
}
GITHUB_ACTIONS = KnownFramework("GitHub Actions", "Tooling", ())


def normalize_package_name(name: str) -> str:
    """Normalize a package name the way pip does: lowercase, with runs of - _ . turned into -."""
    return re.sub(r"[-_.]+", "-", name).lower()


FRAMEWORKS_BY_PACKAGE = {
    normalize_package_name(package): framework
    for framework in KNOWN_FRAMEWORKS
    for package in framework.packages
}
FRAMEWORKS_BY_IMPORT = {
    import_name: framework
    for framework in KNOWN_FRAMEWORKS
    for import_name in framework.imports
}


@dataclass
class Framework:
    """A framework found in the repository, with the evidence for it."""

    name: str
    category: str
    source: str
    file: str
    line: int | None = None


@dataclass
class DetectionResult:
    """All frameworks found, plus the files that could not be read."""

    frameworks: list[Framework] = field(default_factory=list)
    unparsed_files: list[str] = field(default_factory=list)

    def undeclared(self) -> list[Framework]:
        """Return frameworks the code imports but no dependency file declares."""
        return [framework for framework in self.frameworks if framework.source == SOURCE_IMPORT]


def detect_frameworks(repo_path: Path, scan: ScanResult) -> DetectionResult:
    """Find frameworks from dependency files, config files and Python imports."""
    found: dict[str, Framework] = {}
    unparsed: list[str] = []

    def add(known: KnownFramework, source: str, file: str, line: int | None = None) -> None:
        # The first evidence wins. Dependency files are checked first,
        # so a declared framework is never reported as undeclared.
        if known.name not in found:
            found[known.name] = Framework(known.name, known.category, source, file, line)

    file_paths = [file.path for file in scan.files]

    for path in file_paths:
        try:
            for package, line in read_dependency_file(repo_path / path):
                known = FRAMEWORKS_BY_PACKAGE.get(normalize_package_name(package))
                if known:
                    add(known, SOURCE_DEPENDENCY, path, line)
        except (tomli.TOMLDecodeError, json.JSONDecodeError, AttributeError, TypeError):
            unparsed.append(path)

    for path in file_paths:
        known = find_config_framework(path)
        if known:
            add(known, SOURCE_CONFIG, path)

    local_modules = find_local_module_names(file_paths)
    for path in file_paths:
        try:
            imports = read_python_imports(repo_path / path)
        except (SyntaxError, ValueError, json.JSONDecodeError):
            unparsed.append(path)
            continue
        for import_name, line in imports:
            known = FRAMEWORKS_BY_IMPORT.get(import_name)
            if known and import_name not in local_modules:
                add(known, SOURCE_IMPORT, path, line)

    frameworks = sorted(found.values(), key=lambda framework: (framework.category, framework.name))
    return DetectionResult(frameworks, sorted(unparsed))


def read_dependency_file(path: Path) -> list[tuple[str, int | None]]:
    """Return (package name, line number or None) for every dependency in a dependency file."""
    name = path.name
    if name.startswith("requirements") and name.endswith(".txt"):
        return read_requirements_txt(path)
    if name == "pyproject.toml":
        return [(package, None) for package in read_pyproject_toml(path)]
    if name == "package.json":
        return [(package, None) for package in read_package_json(path)]
    return []


def read_requirements_txt(path: Path) -> list[tuple[str, int]]:
    """Read package names from a requirements file, skipping comments and pip options."""
    packages = []
    text = path.read_text(encoding="utf-8", errors="replace")
    for line_number, line in enumerate(text.splitlines(), start=1):
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        match = PACKAGE_NAME_PATTERN.match(line)
        if match:
            packages.append((match.group(), line_number))
    return packages


def read_pyproject_toml(path: Path) -> list[str]:
    """Read package names from standard, optional, group and Poetry dependencies."""
    with open(path, "rb") as file:
        data = tomli.load(file)

    requirements = list(data.get("project", {}).get("dependencies", []))
    for group in data.get("project", {}).get("optional-dependencies", {}).values():
        requirements.extend(group)
    for group in data.get("dependency-groups", {}).values():
        # Entries can also be {"include-group": "..."}; only strings are packages.
        requirements.extend(entry for entry in group if isinstance(entry, str))

    poetry = data.get("tool", {}).get("poetry", {})
    poetry_packages = list(poetry.get("dependencies", {}))
    for group in poetry.get("group", {}).values():
        poetry_packages.extend(group.get("dependencies", {}))

    names = [match.group() for match in map(PACKAGE_NAME_PATTERN.match, requirements) if match]
    return names + [name for name in poetry_packages if name != "python"]


def read_package_json(path: Path) -> list[str]:
    """Read package names from the dependency sections of a package.json file."""
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    packages = []
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        packages.extend(data.get(section, {}))
    return packages


def find_config_framework(path: str) -> KnownFramework | None:
    """Return the tool a configuration file belongs to, if any."""
    if path.startswith(".github/workflows/"):
        return GITHUB_ACTIONS
    return CONFIG_FILE_FRAMEWORKS.get(Path(path).name)


def find_local_module_names(file_paths: list[str]) -> set[str]:
    """Return the names of the repository's own Python modules and packages.

    An import of one of these (for example "import flask" inside the Flask repository)
    is the project's own code, not a third-party framework.
    """
    names = set()
    for path in file_paths:
        if path.endswith(".py"):
            parts = Path(path).with_suffix("").parts
            names.update(parts)
    return names


def read_python_imports(path: Path) -> list[tuple[str, int | None]]:
    """Return (top-level module name, line number) for each import in a .py file or notebook."""
    if path.suffix == ".py":
        source = path.read_text(encoding="utf-8", errors="replace")
        return find_imports(source)
    if path.suffix == ".ipynb":
        return [(name, None) for name, _ in read_notebook_imports(path)]
    return []


def read_notebook_imports(path: Path) -> list[tuple[str, int]]:
    """Return the imports from all code cells of a Jupyter notebook.

    Lines starting with % or ! are notebook commands (for example "!pip install pandas"),
    not Python, so they are removed. A cell that still does not parse is skipped,
    because notebooks often contain unfinished cells.
    """
    notebook = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    imports = []
    for cell in notebook.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        source = cell.get("source", "")
        if isinstance(source, list):
            source = "".join(source)
        lines = ["" if line.lstrip().startswith(("%", "!")) else line for line in source.splitlines()]
        try:
            imports.extend(find_imports("\n".join(lines)))
        except SyntaxError:
            continue
    return imports


def find_imports(source: str) -> list[tuple[str, int]]:
    """Parse Python source code and return (top-level module name, line number), in line order.

    Relative imports such as "from . import utils" are skipped: they always refer to the project itself.
    """
    imports = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((alias.name.split(".")[0], node.lineno))
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imports.append((node.module.split(".")[0], node.lineno))
    return sorted(imports, key=lambda item: item[1])