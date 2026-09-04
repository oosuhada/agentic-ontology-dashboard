from __future__ import annotations

from pathlib import Path

import pytest

from systems.verify_architecture import DOMAINS, verify


def _write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture()
def strict_tree(tmp_path: Path) -> Path:
    app = tmp_path / "systems/backend/app"
    for name in DOMAINS | {"common", "infra", "operations"}:
        (app / name).mkdir(parents=True, exist_ok=True)
        _write(app / name / "__init__.py")
    _write(app / "main.py", "from app.application import create_app\napp = create_app()\n")
    _write(tmp_path / "systems/backend/Dockerfile", 'CMD ["uvicorn", "app.main:app"]\n')
    _write(tmp_path / "systems/backend/render_start.sh", "uvicorn app.main:app\n")
    _write(tmp_path / "scripts/run_local.sh", "uvicorn app.main:app\n")
    _write(tmp_path / "scripts/run_public_api.sh", "uvicorn app.main:app\n")
    _write(
        tmp_path / "systems/frontend/playwright.config.ts",
        """export default {
  webServer: [
    {
      command: `PYTHONPATH=../../systems/backend:../../ml/src python -m uvicorn app.main:app --app-dir ../../systems/backend --host 127.0.0.1 --port 8200`,
    },
  ],
};
""",
    )
    assert verify(tmp_path) == []
    return tmp_path


@pytest.mark.parametrize(
    ("relative", "content", "rule"),
    [
        ("systems/backend/ontology_dashboard/__init__.py", "", "ARC002"),
        ("systems/backend/app/routers/__init__.py", "", "ARC003"),
        ("systems/backend/app/common/bad.py", "from app.identity import Principal\n", "ARC004"),
        (
            "systems/backend/app/dashboard/bad.py",
            "from app.report.report_service import ReportService\n",
            "ARC005",
        ),
        (
            "systems/backend/app/dashboard/bad.py",
            "from app.report.report_repository import ReportRepository\n",
            "ARC005",
        ),
        (
            "systems/backend/app/diagnosis/bad.py",
            "from app.equipment.adapters.fixture_repository import FixtureEquipmentRepository\n",
            "ARC005",
        ),
        ("systems/backend/app/diagnosis/bad.py", "import fastapi\n", "ARC006"),
        (
            "systems/backend/app/dataset/bad.py",
            "from app.infra.db.dataset_repository import DatasetRepository\n",
            "ARC014",
        ),
        (
            "systems/backend/app/operations/bad.py",
            "from app.infra.db.dashboard_repository import DashboardRepository\n",
            "ARC013",
        ),
        (
            "systems/backend/app/infra/bad.py",
            "from app.diagnosis.diagnosis_service import DiagnosisService\n",
            "ARC008",
        ),
        (
            "systems/backend/app/infra/bad.py",
            "from app.diagnosis.predictor import configured_predictor\n",
            "ARC008",
        ),
        (
            "systems/backend/app/runtime_bad.py",
            "from systems.generator.model import model_training\n",
            "ARC009",
        ),
        (
            "systems/backend/app/runtime_bad.py",
            "import ontology_dashboard.main\n",
            "ARC010",
        ),
        (
            "systems/backend/app/dependencies.py",
            'QUERY = "SELECT * FROM things"\n',
            "ARC012",
        ),
        (
            "systems/backend/app/runtime_bad.py",
            'ARTIFACT = "../generator/model_store/current"\n',
            "ARC012",
        ),
        ("systems/backend/app/runtime_bad.py", "<<<<<<< HEAD\n", "ARC000"),
    ],
)
def test_strict_verifier_rejects_regressions(
    strict_tree: Path,
    relative: str,
    content: str,
    rule: str,
) -> None:
    _write(strict_tree / relative, content)
    violations = verify(strict_tree)
    assert any(item.rule == rule for item in violations), [str(item) for item in violations]


def test_strict_verifier_rejects_legacy_runtime_entrypoint(strict_tree: Path) -> None:
    _write(
        strict_tree / "systems/backend/Dockerfile",
        'CMD ["uvicorn", "ontology_dashboard.app:app"]\n',
    )
    violations = verify(strict_tree)
    assert {item.rule for item in violations} >= {"ARC010", "ARC011"}


def test_strict_verifier_requires_playwright_backend_app_dir(strict_tree: Path) -> None:
    _write(
        strict_tree / "systems/frontend/playwright.config.ts",
        """export default {
  webServer: [
    {
      command: `PYTHONPATH=../../systems/backend:../../ml/src python -m uvicorn app.main:app --host 127.0.0.1 --port 8200`,
    },
  ],
};
""",
    )
    violations = verify(strict_tree)
    assert any(
        item.rule == "ARC011" and "--app-dir ../../systems/backend" in item.detail
        for item in violations
    ), [str(item) for item in violations]


def test_strict_verifier_rejects_repo_root_first_playwright_pythonpath(strict_tree: Path) -> None:
    _write(
        strict_tree / "systems/frontend/playwright.config.ts",
        """export default {
  webServer: [
    {
      command: `PYTHONPATH=../..:../../systems/backend:../../ml/src python -m uvicorn app.main:app --app-dir ../../systems/backend --host 127.0.0.1 --port 8200`,
    },
  ],
};
""",
    )
    violations = verify(strict_tree)
    assert any(
        item.rule == "ARC011" and "repository root" in item.detail
        for item in violations
    ), [str(item) for item in violations]


def test_strict_verifier_allows_public_cross_context_boundaries(strict_tree: Path) -> None:
    _write(
        strict_tree / "systems/backend/app/operations/good.py",
        "\n".join(
            [
                "from app.diagnosis.ports import PredictionResultRepositoryPort",
                "from app.diagnosis.schemas import PredictionResult",
                "from app.ontology.ontology_domain import ObjectRecord",
                "from app.report.ports import ReportRepositoryPort",
                "",
            ]
        ),
    )
    assert verify(strict_tree) == []


@pytest.mark.parametrize(
    ("module", "symbol"),
    [
        ("app.equipment", "EquipmentService"),
        ("app.dashboard", "DashboardService"),
        ("app.ontology", "OntologyService"),
    ],
)
def test_strict_verifier_rejects_cross_context_package_root_concrete_services(
    strict_tree: Path,
    module: str,
    symbol: str,
) -> None:
    _write(
        strict_tree / "systems/backend/app/operations/bad.py",
        f"from {module} import {symbol}\n",
    )
    violations = verify(strict_tree)
    assert any(item.rule == "ARC005" for item in violations), [str(item) for item in violations]
