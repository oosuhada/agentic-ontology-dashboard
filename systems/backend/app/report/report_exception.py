from __future__ import annotations


class ReportConflictError(RuntimeError):
    status_code = 409
    code = "report_revision_conflict"
    message = "다른 사용자가 보고서를 수정했습니다. 최신 revision을 다시 불러오세요."


__all__ = ["ReportConflictError"]
