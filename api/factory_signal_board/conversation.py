from __future__ import annotations

import re
from dataclasses import dataclass

from .contracts import Intent


@dataclass(frozen=True)
class IntentResult:
    intent: Intent
    supported: bool
    reason: str


INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous",
    r"system\s+prompt",
    r"developer\s+message",
    r"<script",
    r"javascript:",
    r"drop\s+table",
    r"curl\s+https?://",
    r"설비.*(정지|제어).*(실행|해줘)",
    r"이전.*지시.*무시",
]


class IntentRouter:
    def route(self, question: str) -> IntentResult:
        normalized = " ".join(question.strip().lower().split())
        if any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in INJECTION_PATTERNS):
            return IntentResult("overview", False, "unsafe_or_out_of_scope_instruction")

        rules: list[tuple[Intent, tuple[str, ...]]] = [
            ("summarize-manager", ("매니저용", "관리자용", "짧게 요약", "manager summary")),
            ("detail-engineer", ("엔지니어용", "근거를 자세히", "기술적으로", "engineer detail")),
            ("recommend-check", ("무엇을 먼저 점검", "점검 순서", "점검해야", "what should i inspect")),
            ("show-model-details", ("모델 상세", "임계값", "모델 버전", "model details")),
            ("compare", ("정상 설비와 비교", "이전과 비교", "비교해", "compare")),
            ("explain-risk", ("왜 위험", "가장 크게 영향", "어떤 센서", "why", "influence")),
        ]
        for intent, keywords in rules:
            if any(keyword in normalized for keyword in keywords):
                return IntentResult(intent, True, "matched_supported_intent")

        if normalized in {"요약", "현재 상태", "overview", "상태 알려줘"}:
            return IntentResult("overview", True, "matched_overview")
        return IntentResult("overview", False, "unsupported_question")


def deterministic_answer(intent: Intent, evidence: dict, supported: bool) -> str:
    if not supported:
        return (
            "현재 사건의 위험 근거, 센서 비교, 역할별 요약, 점검 순서와 모델 상세만 답할 수 있습니다. "
            "실제 설비 제어, 근거 없는 원인 확정 또는 Evidence 밖의 질문은 수행하지 않습니다."
        )
    if evidence["status"] == "data_quality_hold":
        return "센서 데이터 품질 문제로 위험 판단을 보류했습니다. 데이터 검증과 재수집을 먼저 진행해야 합니다."

    factors = evidence["top_factors"]
    primary = factors[0] if factors else None
    if intent == "explain-risk" and primary:
        return (
            f"가장 큰 근거는 {primary['display_name']} {primary['value']:,.2f}{primary['unit']}입니다. "
            f"참고 범위는 {primary['normal_range']}이며, 현장 점검으로 원인을 확인해야 합니다."
        )
    if intent == "compare":
        return "현재 관측과 fixture 내 이전 관측을 비교하도록 센서 차트와 근거 표를 재구성했습니다. 외부 정상군 통계는 사용하지 않았습니다."
    if intent == "summarize-manager":
        return f"현재 상태는 {evidence['status']}이며 권장 결정은 {evidence['recommended_decision']}입니다."
    if intent == "detail-engineer":
        return "이상 구간, 센서 변화, 주요 기여 요인과 점검 체크리스트를 기술 상세 순서로 재구성했습니다."
    if intent == "recommend-check":
        checks = evidence["maintenance_context"]["checklist"]
        return "우선 점검 순서는 다음과 같습니다: " + " → ".join(checks)
    if intent == "show-model-details":
        return (
            f"모델 버전은 {evidence['model']['model_version']}, 정책 버전은 {evidence['model']['policy_version']}, "
            f"표시 임계값은 {evidence['threshold']:.2f}입니다."
        )
    return f"현재 상태는 {evidence['status']}이고 신뢰도는 {evidence['confidence']}입니다."
