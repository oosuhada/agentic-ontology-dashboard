"""Repository for loading and finding versioned static mapping files."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from systems.generator.generator_config import PATHS, PROJECT_ROOT
from systems.generator.app.extraction.extraction_exception import (
    ExtractionMappingNotFoundError,
    ExtractionSourcePathUnsupportedError,
)

logger = logging.getLogger(__name__)


class MappingRepository:
    """Loads and caches static mapping tables from verified locations."""

    def __init__(
        self,
        mapping_root: Optional[Path] = None,
        search_roots: Optional[list[Path]] = None,
    ) -> None:
        default_roots = [
            mapping_root or (PATHS.ontology / "mappings"),
            PROJECT_ROOT / "contracts" / "examples" / "generator-protocol-extraction",
            PROJECT_ROOT / "contracts" / "test-vectors" / "generator-protocol-extraction-v1" / "input",
            PATHS.data_dir / "mappings",
        ]
        self.search_roots = search_roots or default_roots

    def find_mapping_file(
        self,
        mapping_id: str,
        mapping_version: str,
    ) -> Path:
        """Locate static mapping JSON file by mapping_id and mapping_version."""
        clean_id = mapping_id.strip()
        clean_ver = mapping_version.strip()

        if ".." in clean_id or "/" in clean_id or "\\" in clean_id or ".." in clean_ver:
            raise ExtractionSourcePathUnsupportedError(
                f"매핑 식별자에 허용되지 않는 경로 문자가 포함되어 있습니다: id='{mapping_id}', ver='{mapping_version}'"
            )

        candidate_paths = []
        for root in self.search_roots:
            candidate_paths.extend([
                root / clean_id / clean_ver / "mapping.json",
                root / clean_id / f"{clean_ver}.json",
                root / f"{clean_id}_{clean_ver}.json",
                root / f"{clean_id}.json",
            ])
            if root.is_dir():
                for cand_file in root.rglob("*.json"):
                    candidate_paths.append(cand_file)

        candidate_paths.extend([
            PATHS.ontology / "mappings" / clean_id / clean_ver / "mapping.json",
            PATHS.ontology / "mappings" / clean_id / f"{clean_ver}.json",
            PATHS.ontology / "mappings" / f"{clean_id}_{clean_ver}.json",
            PATHS.ontology / "mappings" / f"{clean_id}.json",
            PATHS.data_dir / "mappings" / clean_id / f"{clean_ver}.json",
            PROJECT_ROOT / "contracts" / "examples" / "generator-protocol-extraction" / "static-mapping-table.json",
            PROJECT_ROOT / "contracts" / "test-vectors" / "generator-protocol-extraction-v1" / "input" / "static-mapping-table.json",
        ])

        for cand in candidate_paths:
            if cand.is_file():
                try:
                    data = json.loads(cand.read_text(encoding="utf-8"))
                    if data.get("mapping_id") == clean_id and str(data.get("mapping_version")) == clean_ver:
                        return cand.resolve()
                except Exception:
                    continue

        raise ExtractionMappingNotFoundError(
            f"승인된 정적 매핑 파일을 찾을 수 없습니다: mapping_id='{mapping_id}', mapping_version='{mapping_version}'",
            details=[{"mapping_id": clean_id, "mapping_version": clean_ver}],
        )

    def load_mapping(
        self,
        mapping_id: str,
        mapping_version: str,
    ) -> tuple[dict[str, Any], Path]:
        """Load mapping dictionary and resolved path."""
        path = self.find_mapping_file(mapping_id, mapping_version)
        try:
            content = path.read_text(encoding="utf-8")
            data = json.loads(content)
            return data, path
        except Exception as exc:
            raise ExtractionMappingNotFoundError(
                f"매핑 파일 로드 실패 ({path.name}): {exc}",
                details=[{"path": str(path)}],
            ) from exc
