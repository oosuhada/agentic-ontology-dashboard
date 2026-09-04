from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Iterable

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .ports import (
    DashboardSnapshotPort,
    DiagnosisEvidencePort,
    MaintenanceHistoryPort,
    ReportAuditPort,
    ReportPrincipal,
    ReportRepositoryPort,
)
from .report_exception import ReportConflictError
from .report_schema import (
    ExportArtifact,
    ExportCheckpoint,
    ExportRequest,
    ReportDraftRecord,
    ReportDraftSaveRequest,
)


FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    "/System/Library/Fonts/Supplemental/NotoSansGothic-Regular.ttf",
    "/Library/Fonts/NotoSansKR-Regular.otf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "C:/Windows/Fonts/malgun.ttf",
)


class ReportService:
    def __init__(
        self,
        *,
        repository: ReportRepositoryPort,
        dashboard: DashboardSnapshotPort,
        diagnosis: DiagnosisEvidencePort,
        maintenance: MaintenanceHistoryPort,
        audit: ReportAuditPort,
    ) -> None:
        self.repository = repository
        self.dashboard = dashboard
        self.diagnosis = diagnosis
        self.maintenance = maintenance
        self.audit = audit
        self._font_name, self._unicode_font = self._register_font()

    def get_draft(
        self,
        *,
        workspace_id: str,
        event_id: str,
        role: str,
        locale: str,
    ) -> ReportDraftRecord | None:
        payload = self.repository.get_draft(
            workspace_id=workspace_id,
            event_id=event_id,
            role=role,
            locale=locale,
        )
        return ReportDraftRecord.model_validate(payload) if payload is not None else None

    def save_draft(
        self,
        *,
        principal: ReportPrincipal,
        request: ReportDraftSaveRequest,
    ) -> ReportDraftRecord:
        try:
            payload = self.repository.save_draft(
                workspace_id=request.workspace_id,
                event_id=request.event_id,
                role=request.role,
                locale=request.locale,
                base_revision=request.base_revision,
                headline=request.headline,
                summary=request.summary,
                sections=[section.model_dump(mode="json") for section in request.sections],
                content_origin=request.content_origin,
                source_locale=request.source_locale,
                source_revision=request.source_revision,
                updated_by=principal.user_id,
            )
        except ReportConflictError:
            raise
        return ReportDraftRecord.model_validate(payload)

    @staticmethod
    def _canonical_json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)

    @staticmethod
    def _slug(value: str) -> str:
        normalized = re.sub(r"[^0-9A-Za-z가-힣_-]+", "-", value.strip()).strip("-")
        return normalized[:80] or "ontology-dashboard"

    @staticmethod
    def _register_font() -> tuple[str, bool]:
        configured = os.getenv("EXPORT_PDF_FONT")
        candidates = ([configured] if configured else []) + list(FONT_CANDIDATES)
        for candidate in candidates:
            if not candidate:
                continue
            path = Path(candidate)
            if not path.exists():
                continue
            try:
                pdfmetrics.registerFont(TTFont("OntologyExportFont", str(path)))
                return "OntologyExportFont", True
            except Exception:
                continue
        return "Helvetica", False

    def _safe_text(self, value: Any) -> str:
        text = str(value)
        if self._unicode_font:
            return text
        return text.encode("latin-1", errors="replace").decode("latin-1")

    def _snapshot(
        self,
        *,
        principal: ReportPrincipal,
        request: ExportRequest,
    ) -> dict[str, Any]:
        project_context = self.repository.resolve_scope(
            request.workspace_id,
            expected_organization_id=principal.organization_id,
            expected_project_id=principal.active_project_id,
        )
        if request.scope == "dashboard":
            content = self.dashboard.dashboard_snapshot(
                principal=principal,
                workspace_id=request.workspace_id,
            )
        elif request.scope == "event":
            assert request.event_id is not None
            content = self.diagnosis.event_report_snapshot(
                event_id=request.event_id,
                principal=principal,
            )
        else:
            content = self.maintenance.role_workspace_snapshot(
                principal=principal,
                workspace_id=request.workspace_id,
            )
        return {
            "export_schema_version": "1.0",
            "organization_id": project_context.organization_id,
            "project_id": project_context.project_id,
            "workspace_id": request.workspace_id,
            "scope": request.scope,
            "event_id": request.event_id,
            "requested_by": {
                "user_id": principal.user_id,
                "display_name": principal.display_name,
                "roles": principal.roles,
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "content": content,
        }

    @classmethod
    def _flatten(cls, value: Any, prefix: str = "") -> Iterable[tuple[str, str]]:
        if isinstance(value, dict):
            for key in sorted(value):
                child = f"{prefix}.{key}" if prefix else str(key)
                yield from cls._flatten(value[key], child)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                child = f"{prefix}[{index}]"
                yield from cls._flatten(item, child)
        else:
            if value is None:
                rendered = ""
            elif isinstance(value, bool):
                rendered = "true" if value else "false"
            else:
                rendered = str(value)
            yield prefix, rendered

    def _json_bytes(self, snapshot: dict[str, Any]) -> bytes:
        return json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True, default=str).encode("utf-8")

    def _csv_bytes(self, snapshot: dict[str, Any]) -> bytes:
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["path", "value"])
        for path, value in self._flatten(snapshot):
            writer.writerow([path, value])
        return output.getvalue().encode("utf-8-sig")

    def _pdf_bytes(
        self,
        *,
        snapshot: dict[str, Any],
        title: str,
        snapshot_hash: str,
    ) -> bytes:
        output = io.BytesIO()
        document = SimpleDocTemplate(
            output,
            pagesize=A4,
            leftMargin=16 * mm,
            rightMargin=16 * mm,
            topMargin=15 * mm,
            bottomMargin=15 * mm,
            title=self._safe_text(title),
            author=self._safe_text("Ontology Dashboard"),
        )
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "ExportTitle",
            parent=styles["Title"],
            fontName=self._font_name,
            fontSize=18,
            leading=24,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#101828"),
            spaceAfter=10,
        )
        heading_style = ParagraphStyle(
            "ExportHeading",
            parent=styles["Heading2"],
            fontName=self._font_name,
            fontSize=11,
            leading=15,
            textColor=colors.HexColor("#344054"),
            spaceBefore=8,
            spaceAfter=6,
        )
        body_style = ParagraphStyle(
            "ExportBody",
            parent=styles["BodyText"],
            fontName=self._font_name,
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#475467"),
        )
        small_style = ParagraphStyle(
            "ExportSmall",
            parent=body_style,
            fontSize=7,
            leading=9,
            textColor=colors.HexColor("#667085"),
        )
        story: list[Any] = [
            Paragraph(escape(self._safe_text(title)), title_style),
            Paragraph(
                escape(self._safe_text(f"Snapshot SHA-256: {snapshot_hash}")),
                small_style,
            ),
            Spacer(1, 5 * mm),
        ]
        metadata_rows = [
            ["Workspace", snapshot["workspace_id"]],
            ["Scope", snapshot["scope"]],
            ["Event", snapshot.get("event_id") or "-"],
            ["Requested by", snapshot["requested_by"]["display_name"]],
            ["Generated at", snapshot["generated_at"]],
        ]
        table = Table(
            [
                [
                    Paragraph(escape(self._safe_text(key)), body_style),
                    Paragraph(escape(self._safe_text(value)), body_style),
                ]
                for key, value in metadata_rows
            ],
            colWidths=[34 * mm, 130 * mm],
            repeatRows=0,
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F2F4F7")),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D0D5DD")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.extend([table, Spacer(1, 5 * mm), Paragraph(self._safe_text("Snapshot fields"), heading_style)])
        rows = list(self._flatten(snapshot["content"]))
        max_rows = 260
        for index in range(0, min(len(rows), max_rows), 34):
            chunk = rows[index : index + 34]
            data = [[Paragraph(self._safe_text("Path"), body_style), Paragraph(self._safe_text("Value"), body_style)]]
            for path, value in chunk:
                rendered_value = value if len(value) <= 500 else value[:497] + "..."
                data.append(
                    [
                        Paragraph(escape(self._safe_text(path)), small_style),
                        Paragraph(escape(self._safe_text(rendered_value)).replace("\n", "<br/>"), small_style),
                    ]
                )
            field_table = Table(data, colWidths=[65 * mm, 99 * mm], repeatRows=1)
            field_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAECF0")),
                        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D0D5DD")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 4),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ]
                )
            )
            story.append(field_table)
            if index + 34 < min(len(rows), max_rows):
                story.append(PageBreak())
        if len(rows) > max_rows:
            story.extend(
                [
                    Spacer(1, 3 * mm),
                    Paragraph(
                        escape(self._safe_text(f"PDF summary truncated after {max_rows} fields. Use JSON export for the complete snapshot.")),
                        small_style,
                    ),
                ]
            )
        document.build(story)
        return output.getvalue()

    def create_export(
        self,
        *,
        principal: ReportPrincipal,
        request: ExportRequest,
    ) -> ExportArtifact:
        snapshot = self._snapshot(principal=principal, request=request)
        snapshot_json = self._canonical_json(snapshot)
        snapshot_hash = hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()
        title = request.title or f"Ontology Dashboard {request.scope.title()} Export"
        stem_parts = [request.workspace_id, request.scope]
        if request.event_id:
            stem_parts.append(request.event_id)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = self._slug("-".join(stem_parts)) + f"-{timestamp}.{request.format}"
        if request.format == "json":
            content = self._json_bytes(snapshot)
            media_type = "application/json; charset=utf-8"
        elif request.format == "csv":
            content = self._csv_bytes(snapshot)
            media_type = "text/csv; charset=utf-8"
        else:
            content = self._pdf_bytes(snapshot=snapshot, title=title, snapshot_hash=snapshot_hash)
            media_type = "application/pdf"
        content_hash = hashlib.sha256(content).hexdigest()
        checkpoint_payload = self.repository.create_checkpoint(
            workspace_id=request.workspace_id,
            scope=request.scope,
            export_format=request.format,
            event_id=request.event_id,
            filename=filename,
            media_type=media_type,
            content_bytes=len(content),
            snapshot_hash=snapshot_hash,
            content_hash=content_hash,
            requested_by=principal.user_id,
            requested_by_name=principal.display_name,
            snapshot=snapshot,
        )
        audit = self.audit.record_report_audit(
            event_id=request.event_id,
            run_id=checkpoint_payload["id"],
            action="export.created",
            model_version=None,
            payload=checkpoint_payload,
        )
        checkpoint_payload["audit_id"] = audit["id"]
        checkpoint = ExportCheckpoint.model_validate(
            {key: value for key, value in checkpoint_payload.items() if key != "audit_id"}
        )
        return ExportArtifact(checkpoint=checkpoint, content=content)

    def list_checkpoints(
        self,
        *,
        principal: ReportPrincipal,
        workspace_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self.repository.list_checkpoints(
            requested_by=None if principal.is_admin else principal.user_id,
            workspace_id=workspace_id,
            limit=limit,
        )


ExportService = ReportService

__all__ = ["ExportService", "ReportService"]
