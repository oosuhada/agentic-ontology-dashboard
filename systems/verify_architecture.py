"""Final strict architecture checks for the working Operations.

The migration is finished: this verifier protects the resulting shape instead
of tracking a legacy-source baseline. It intentionally uses only the Python
standard library so CI can run it before installing project dependencies.
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = Path("systems/backend")
APP = BACKEND / "app"
LEGACY = BACKEND / "ontology_dashboard"

DOMAINS = {
    "identity",
    "project",
    "ontology",
    "equipment",
    "dataset",
    "diagnosis",
    "maintenance",
    "dashboard",
    "report",
    "planner",
    "governance",
}
BOUNDARY_CONTEXTS = DOMAINS | {"operations"}
REQUIRED_APP_DIRS = DOMAINS | {"common", "infra", "operations"}
FORBIDDEN_APP_TOP_LEVEL = {
    "runtime",
    "routers",
    "adapters",
    "closed_loop",
    "orchestration",
    "integrations",
    "modeling",
    "domain_packs",
    "predictive_maintenance_runtime",
}
PUBLIC_BOUNDARY_MODULES = {"domain", "ports", "contracts", "schemas"}
PUBLIC_BOUNDARY_SUFFIXES = ("_domain", "_schema", "_contracts")
TECHNICAL_IMPORT_PREFIXES = (
    "fastapi",
    "sqlite3",
    "psycopg",
    "sqlalchemy",
    "httpx",
    "requests",
    "boto3",
    "redis",
)
COMPOSITION_FILES = {
    "main.py",
    "dependencies.py",
    "application.py",
    "health.py",
    "error_handlers.py",
}
RUNTIME_ENTRYPOINT_FILES = (
    Path("systems/backend/Dockerfile"),
    Path("systems/backend/render_start.sh"),
    Path("scripts/run_local.sh"),
    Path("scripts/run_public_api.sh"),
    Path("systems/frontend/playwright.config.ts"),
)
IGNORED_PARTS = {".git", ".venv", "node_modules", "dist", "__pycache__"}


@dataclass(frozen=True)
class Violation:
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.rule} {self.detail}"


def _playwright_backend_webserver_command(playwright_text: str) -> str | None:
    """Extract the single uvicorn command configured in Playwright webServer."""

    matches = list(
        re.finditer(
            r"^(?P<indent>\s*)webServer\s*:",
            playwright_text,
            flags=re.MULTILINE,
        )
    )
    if len(matches) != 1:
        return None
    match = matches[0]
    indent = match.group("indent")
    following = playwright_text[match.end() :]
    next_property = re.search(
        rf"^{re.escape(indent)}[A-Za-z_$][A-Za-z0-9_$]*\s*:",
        following,
        flags=re.MULTILINE,
    )
    end = match.end() + next_property.start() if next_property is not None else len(playwright_text)
    block = playwright_text[match.start() : end]
    commands = re.findall(
        r"^\s*command:\s*`([^`]*)`",
        block,
        flags=re.MULTILINE | re.DOTALL,
    )
    backend = [command for command in commands if re.search(r"\buvicorn\b", command)]
    return backend[0] if len(backend) == 1 else None


def _python_files(root: Path, relative: Path) -> list[Path]:
    base = root / relative
    return [] if not base.exists() else [p for p in base.rglob("*.py") if not _ignored(p, root)]


def _ignored(path: Path, root: Path) -> bool:
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return True
    return any(part in IGNORED_PARTS for part in parts)


def _imports(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.append((node.lineno, node.module))
        elif isinstance(node, ast.Call):
            function = node.func
            dynamic = (
                isinstance(function, ast.Name) and function.id == "__import__"
            ) or (
                isinstance(function, ast.Attribute)
                and function.attr == "import_module"
            )
            if dynamic and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                result.append((node.lineno, node.args[0].value))
    return result


def _runtime_string_literals(path: Path) -> list[tuple[int, str]]:
    """Return executable/configuration string literals, excluding docstrings."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstring_nodes: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (
            isinstance(body, list)
            and body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            docstring_nodes.add(id(body[0].value))
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstring_nodes
    ]


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _is_public_context_import(module: str, *, source_context: str) -> bool:
    """Return whether a cross-context app import uses an explicit public seam.

    Cross-context imports must name a domain/port/contract/schema module.
    Package-root facades are intentionally rejected because they can re-export
    concrete services and silently bypass dependency inversion.
    """

    parts = module.split(".")
    if len(parts) < 2 or parts[0] != "app":
        return True
    target = parts[1]
    if target == source_context or target in {"common", "infra"}:
        return True
    if target not in BOUNDARY_CONTEXTS:
        return True
    if len(parts) == 2:
        return False
    public_module = parts[2]
    return (
        public_module in PUBLIC_BOUNDARY_MODULES
        or public_module.endswith(PUBLIC_BOUNDARY_SUFFIXES)
    )


def verify(root: Path = ROOT) -> list[Violation]:
    errors: list[Violation] = []
    app_root = root / APP

    # ARC001 / ARC002: one physical Backend package root.
    if not app_root.is_dir():
        errors.append(Violation("ARC001", "missing systems/backend/app canonical root"))
    for name in sorted(REQUIRED_APP_DIRS):
        if not (app_root / name).is_dir():
            errors.append(Violation("ARC001", f"missing canonical app/{name} domain"))
    if (root / LEGACY).exists():
        errors.append(Violation("ARC002", "systems/backend/ontology_dashboard must not exist"))

    # ARC003: do not recreate the old layer/technology-first top-level packages.
    for name in sorted(FORBIDDEN_APP_TOP_LEVEL):
        if (app_root / name).exists():
            errors.append(Violation("ARC003", f"forbidden top-level app/{name}"))

    for path in _python_files(root, APP):
        relative = path.relative_to(app_root)
        top = relative.parts[0] if relative.parts else ""
        is_domain = top in DOMAINS
        is_boundary_context = top in BOUNDARY_CONTEXTS
        is_router = path.name.endswith("router.py")
        is_composition = len(relative.parts) == 1 and path.name in COMPOSITION_FILES
        try:
            imports = _imports(path)
        except SyntaxError as exc:
            errors.append(Violation("ARC000", f"{_rel(root, path)} cannot parse: {exc}"))
            continue

        for line, module in imports:
            location = f"{_rel(root, path)}:{line} imports {module}"
            # ARC004 common must remain domain-neutral.
            if top == "common" and any(module == f"app.{d}" or module.startswith(f"app.{d}.") for d in DOMAINS):
                errors.append(Violation("ARC004", location))

            # ARC005 cross-context dependency inversion is allowlist based:
            # only public domain/port/contract/schema seams may be imported.
            if (
                is_boundary_context
                and not is_router
                and module.startswith("app.")
                and not _is_public_context_import(module, source_context=top)
            ):
                errors.append(Violation("ARC005", location))

            # ARC013 Operations is an application boundary, never an infrastructure
            # composition location.  Concrete adapters belong in dependencies.py.
            if top == "operations" and module.startswith("app.infra"):
                errors.append(Violation("ARC013", location))

            # ARC014 domain application/core code may not reach infrastructure
            # implementations directly; ports are implemented from the outside.
            if is_domain and not is_router and module.startswith("app.infra"):
                errors.append(Violation("ARC014", location))

            # ARC006/007 domain use-case/domain/schema files stay framework/SDK free.
            domain_core = is_boundary_context and not is_router and not path.name.startswith("__init__")
            if domain_core and any(module == prefix or module.startswith(prefix + ".") for prefix in TECHNICAL_IMPORT_PREFIXES):
                errors.append(Violation("ARC006", location))

            # ARC008 infra may implement domain ports, never import domain use-case
            # services or rule helpers (including Diagnosis inference/evidence).
            if (
                top == "infra"
                and module.startswith("app.")
                and (
                    module.split(".")[-1].endswith("_service")
                    or module in {"app.diagnosis.evidence", "app.diagnosis.predictor"}
                )
            ):
                errors.append(Violation("ARC008", location))

            # ARC010 no executable code may resurrect the deleted package.
            if module == "ontology_dashboard" or module.startswith("ontology_dashboard."):
                errors.append(Violation("ARC010", location))

        # ARC012 composition root must remain composition-only at a coarse static level.
        if is_composition:
            text = path.read_text(encoding="utf-8")
            if re.search(r"\b(SELECT|INSERT|UPDATE|DELETE)\s+", text, flags=re.IGNORECASE):
                errors.append(Violation("ARC012", f"{_rel(root, path)} contains SQL in composition layer"))

    # ARC009 Backend cannot import Generator implementation directly.
    for path in _python_files(root, BACKEND):
        try:
            imports = _imports(path)
        except SyntaxError:
            continue
        for line, module in imports:
            if module == "systems.generator" or module.startswith("systems.generator."):
                errors.append(Violation("ARC009", f"{_rel(root, path)}:{line} imports {module}"))

    # ARC010 / ARC011 runtime configuration uses the one canonical ASGI host.
    legacy_entrypoint = re.compile(r"(?:ontology_dashboard\.(?:app|main|application)|python\s+-m\s+ontology_dashboard\.)")
    for path in RUNTIME_ENTRYPOINT_FILES:
        absolute = root / path
        if not absolute.exists():
            errors.append(Violation("ARC011", f"missing runtime entrypoint file {path.as_posix()}"))
            continue
        text = absolute.read_text(encoding="utf-8")
        if legacy_entrypoint.search(text):
            errors.append(Violation("ARC010", f"legacy runtime entrypoint in {path.as_posix()}"))
        if path.name in {"Dockerfile", "render_start.sh", "run_local.sh", "run_public_api.sh", "playwright.config.ts"} and "app.main:app" not in text:
            errors.append(Violation("ARC011", f"{path.as_posix()} must launch app.main:app"))

    playwright_path = root / "systems/frontend/playwright.config.ts"
    if playwright_path.exists():
        playwright_text = playwright_path.read_text(encoding="utf-8")
        command = _playwright_backend_webserver_command(playwright_text)
        if command is None:
            errors.append(Violation("ARC011", "Playwright must define exactly one uvicorn backend webServer command"))
        else:
            if not re.search(r"\buvicorn\s+app\.main:app(?:\s|$)", command):
                errors.append(Violation("ARC011", "Playwright backend must launch app.main:app"))
            if "ontology_dashboard.main:app" in command:
                errors.append(Violation("ARC010", "Playwright backend must not launch ontology_dashboard.main:app"))
            if not re.search(r"--app-dir\s+\.\./\.\./systems/backend(?:\s|$)", command):
                errors.append(Violation("ARC011", "Playwright backend must pin --app-dir ../../systems/backend"))
            if "PYTHONPATH=../..:" in command:
                errors.append(Violation("ARC011", "Playwright backend must not put repository root ahead of systems/backend"))

    main_path = app_root / "main.py"
    if main_path.exists() and "app = create_app()" not in main_path.read_text(encoding="utf-8"):
        errors.append(Violation("ARC011", "app/main.py must create the FastAPI application directly"))

    # ARC012 conflict markers and sibling-generator path coupling are permanently forbidden.
    for base in (root / "systems", root / "scripts"):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or _ignored(path, root) or path.suffix in {".pyc", ".png", ".jpg", ".zip", ".gz"}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if line.startswith(("<<<<<<<", "=======", ">>>>>>>")):
                    errors.append(Violation("ARC012", f"{_rel(root, path)}:{number} conflict marker"))
            if path.is_relative_to(app_root) and path.suffix == ".py":
                try:
                    literals = _runtime_string_literals(path)
                except SyntaxError:
                    literals = []
                for number, literal in literals:
                    if re.search(r"\.\./(?:\.\./)*generator(?:/|\\)", literal):
                        errors.append(
                            Violation(
                                "ARC012",
                                f"{_rel(root, path)}:{number} hard-codes sibling Generator path",
                            )
                        )

    return errors


def main() -> int:
    errors = verify(ROOT)
    if errors:
        print("[ARCHITECTURE-CHECK] FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("[ARCHITECTURE-CHECK] PASS")
    print("- systems/backend/app is the only Backend package root")
    print("- legacy package/import/entrypoint reintroduction is blocked")
    print("- canonical domain/common/infra boundaries are statically guarded")
    print("- cross-context imports use public domain/ports/contracts/schemas only")
    print("- app/operations and domain code cannot import infrastructure implementations")
    print("- app.main:app is the runtime host")
    print("- Playwright pins canonical app.main:app with systems/backend app-dir")
    print("- Backend-to-Generator direct imports and unsafe sibling paths are blocked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
