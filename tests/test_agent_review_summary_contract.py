from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from app.operations.agent_review_summary import (
    compose_deterministic_agent_review_summary,
    validate_agent_review_summary,
    validate_agent_review_summary_contract,
    validated_agent_review_summary,
)


ROOT = Path(__file__).resolve().parents[1]
SUMMARY_SCHEMA = json.loads(
    (ROOT / "contracts" / "schemas" / "agent-review-summary.schema.json").read_text(
        encoding="utf-8"
    )
)
PACKET_SCHEMA = json.loads(
    (ROOT / "contracts" / "schemas" / "agent-review-packet.schema.json").read_text(
        encoding="utf-8"
    )
)
PACKET = json.loads(
    (ROOT / "tests" / "fixtures" / "agent_review_packets" / "GS-002.json").read_text(
        encoding="utf-8"
    )
)
GOLD_ROOT = ROOT / "tests" / "fixtures" / "agent_review_packets"


def _valid_summary() -> dict:
    return {
        "schema_version": "agent-review-summary-v1.0",
        "packet_schema_version": PACKET["schema_version"],
        "asset_id": PACKET["asset_id"],
        "generated_at": PACKET["generated_at"],
        "mode": "llm",
        "title": "AI 검토 요약",
        "summary": "공구/마모 계통 중심으로 SOP 근거, 위치 reference, 관측값을 대조해야 합니다.",
        "role_summaries": [
            {
                "role": "field_operator",
                "label": "현장 담당자",
                "quote": "공구/마모 계통을 터렛 공구 홀더 위치에서 먼저 확인하세요.",
                "source_refs": [PACKET["source_refs"][0]],
            },
            {
                "role": "process_manager",
                "label": "공정 관리자",
                "quote": "생산 영향은 패킷 근거와 점검 승인 상태를 함께 봐야 합니다.",
                "source_refs": [PACKET["source_refs"][0]],
            },
        ],
        "history_summary": PACKET["review_draft"]["history_summary"],
        "inspection_focus": [
            {
                "component_id": target["component_id"],
                "component_label": target["component_label"],
                "location_label": target["location_label"],
                "basis_refs": target["basis_refs"],
                "source_refs": [
                    ref
                    for ref in (target["source_ref"], target["location_source_ref"])
                    if ref
                ],
            }
            for target in PACKET["inspection_targets"]
        ],
        "evidence_gaps": PACKET["evidence_gaps"],
        "data_footnotes": [
            {
                "code": gap["field"],
                "note": f"{gap['field']} 데이터가 없어 해당 판단은 보류됩니다.",
                "owner_domain": gap["owner_domain"],
                "source_refs": [PACKET["source_refs"][0]],
            }
            for gap in PACKET["evidence_gaps"]
        ],
        "source_refs": [PACKET["source_refs"][0]],
        "boundary_note": PACKET["review_draft"]["boundary_note"],
        "confidence_label": "grounded",
        "limitations": PACKET["limitations"],
    }


def test_agent_review_summary_schema_accepts_read_only_grounded_summary() -> None:
    summary = _valid_summary()

    assert list(Draft202012Validator(SUMMARY_SCHEMA).iter_errors(summary)) == []
    assert validate_agent_review_summary(summary, packet=PACKET) == []


def test_deterministic_agent_review_summary_validates_all_gold_packets() -> None:
    validator = Draft202012Validator(SUMMARY_SCHEMA)

    for scenario in ("GS-002", "GS-004", "GS-007"):
        packet = json.loads((GOLD_ROOT / f"{scenario}.json").read_text(encoding="utf-8"))
        summary = compose_deterministic_agent_review_summary(packet)

        assert list(validator.iter_errors(summary)) == []
        assert validate_agent_review_summary_contract(summary, packet=packet) == []
        assert summary["mode"] == "deterministic_fallback"
        assert summary["source_refs"] == packet["source_refs"]


def test_deterministic_agent_review_summary_explains_factor_bundle_focus() -> None:
    packet = json.loads((GOLD_ROOT / "GS-004.json").read_text(encoding="utf-8"))

    summary = compose_deterministic_agent_review_summary(packet)
    process_quote = next(
        item["quote"]
        for item in summary["role_summaries"]
        if item["role"] == "process_manager"
    )

    assert summary["confidence_label"] == "partial"
    assert "약 51건" in process_quote
    assert "요청됨 상태" in process_quote
    assert "requested" not in process_quote
    assert len(summary["inspection_focus"]) == 1
    focus = summary["inspection_focus"][0]
    assert focus["component_id"] == "drive_power"
    assert focus["location_label"] == "주축 모터, 커플링, 동력 전달 하우징"
    assert focus["basis_refs"][:3] == [
        "factor.1.mechanical_power_w",
        "factor.2.overstrain_index",
        "factor.3.torque_nm",
    ]
    assert packet["inspection_targets"][0]["location_source_ref"] in packet["source_refs"]
    assert packet["inspection_targets"][0]["location_source_ref"] in focus["source_refs"]


def test_deterministic_agent_review_summary_fails_closed_on_data_quality_hold() -> None:
    packet = json.loads((GOLD_ROOT / "GS-007.json").read_text(encoding="utf-8"))

    summary = compose_deterministic_agent_review_summary(packet)

    assert summary["confidence_label"] == "data_quality_hold"
    assert summary["inspection_focus"] == []
    assert "확정하지 않습니다" in summary["summary"]
    assert "정비" not in summary["summary"]


def test_validated_agent_review_summary_discards_invalid_candidate() -> None:
    bad_candidate = {
        **_valid_summary(),
        "summary": "SOP가 자동 정비 승인 기준이며 정비로 downtime 절감 효과가 입증됐습니다.",
    }

    summary, errors = validated_agent_review_summary(
        packet=PACKET,
        candidate=bad_candidate,
    )

    assert errors == []
    assert summary["mode"] == "deterministic_fallback"
    assert summary["summary"] != bad_candidate["summary"]


def test_agent_review_summary_validator_rejects_prose_only_action_claims() -> None:
    summary = {
        **_valid_summary(),
        "summary": "위험도는 99.9%이며 우선순위 low입니다. 즉시 공구 홀더를 교체하고 정비를 마감 처리하십시오.",
    }

    errors = validate_agent_review_summary_contract(summary, packet=PACKET)

    assert "forbidden_prose_claims:정비를 마감 처리" in errors
    assert any(error.startswith("directive_prose_claims:") for error in errors)
    assert "prose_probability_mismatch:99.9%" in errors
    assert "prose_priority_mismatch:low" in errors


def test_agent_review_summary_validator_rejects_boundary_inversion_and_deleted_limits() -> None:
    summary = {
        **_valid_summary(),
        "boundary_note": "본 요약 확인 시 승인 절차가 자동으로 진행됩니다.",
        "limitations": [],
    }

    errors = validate_agent_review_summary_contract(summary, packet=PACKET)

    assert "boundary_note_mismatch" in errors
    assert "limitations_missing" in errors


def test_agent_review_summary_validator_rejects_available_action_echo_as_command() -> None:
    packet = json.loads((GOLD_ROOT / "GS-004.json").read_text(encoding="utf-8"))
    summary = compose_deterministic_agent_review_summary(packet)
    summary["mode"] = "llm"
    summary["summary"] = "approve_inspection_work_order 를 실행해 승인하십시오."

    errors = validate_agent_review_summary_contract(summary, packet=packet)

    assert "available_action_echo:approve_inspection_work_order" in errors


def test_agent_review_summary_validator_rejects_invented_history_summary() -> None:
    summary = {
        **_valid_summary(),
        "history_summary": [
            "최근 정비 이력: 2026-08-20 스핀들 베어링 교체 완료 · 작업요청 종결"
        ],
    }

    errors = validate_agent_review_summary_contract(summary, packet=PACKET)

    assert "history_summary_mismatch" in errors


def test_agent_review_summary_validator_rejects_uncontracted_domain_claims() -> None:
    summary = _valid_summary()
    summary["role_summaries"] = [
        {
            **summary["role_summaries"][0],
            "quote": "재고 확보 상태라 현재 교대 내 교체 가능하며 납기 보장됩니다.",
        },
        summary["role_summaries"][1],
    ]

    errors = validate_agent_review_summary(summary, packet=PACKET)

    assert any(error.startswith("forbidden_prose_claims:") for error in errors)


def test_deterministic_summary_allows_packet_history_completion_language() -> None:
    packet = {
        **PACKET,
        "review_draft": {
            **PACKET["review_draft"],
            "history_summary": [
                "최근 정비 이력: 스핀들 공구 홀더 교체 완료 · 2026-06-28 · 34일 전",
                *PACKET["review_draft"]["history_summary"][1:],
            ],
        },
    }

    summary = compose_deterministic_agent_review_summary(packet)

    assert validate_agent_review_summary_contract(summary, packet=packet) == []


def test_agent_review_summary_validator_does_not_scan_packet_copied_history_percentages() -> None:
    packet = {
        **PACKET,
        "review_draft": {
            **PACKET["review_draft"],
            "history_summary": [
                *PACKET["review_draft"]["history_summary"][:2],
                "최근 30일 유사 이벤트: 재발률 30%",
            ],
        },
    }

    summary = compose_deterministic_agent_review_summary(packet)

    assert validate_agent_review_summary_contract(summary, packet=packet) == []


def test_agent_review_summary_validator_uses_word_boundaries_for_priority_labels() -> None:
    summary = {
        **_valid_summary(),
        "summary": "follow-up 검토가 필요하며 동력 전달 계통을 highlight 하여 조회합니다.",
    }

    assert validate_agent_review_summary_contract(summary, packet=PACKET) == []


def test_agent_review_summary_validator_accepts_equivalent_probability_formatting() -> None:
    packet = {
        **PACKET,
        "risk_summary": {**PACKET["risk_summary"], "failure_probability": 0.8246},
    }
    summary = {
        **_valid_summary(),
        "summary": "공구/마모 계통은 약 82.46% 위험도로 조회되어 패킷 근거를 대조합니다.",
    }

    assert validate_agent_review_summary_contract(summary, packet=packet) == []


def test_agent_review_summary_validator_rejects_ungrounded_instruction_prose() -> None:
    summary = {
        **_valid_summary(),
        "summary": "공구/마모 계통에서 이상 마모가 확인되었습니다. 즉시 공구 홀더를 교체하십시오.",
    }

    errors = validate_agent_review_summary_contract(summary, packet=PACKET)

    assert any(error.startswith("directive_prose_claims:") for error in errors)


def test_agent_review_summary_validator_rejects_korean_free_text_claims() -> None:
    cases = (
        "베어링 교체가 필요합니다. 교체를 권고합니다.",
        "정비 일정을 잡는 것이 좋겠습니다.",
        "근본 원인은 베어링 마모로 확정되었습니다.",
        "정비 시 약 240분의 다운타임이 절감됩니다.",
        "마지막 정비는 37일 전이며 재발 주기는 12일입니다.",
    )

    for text in cases:
        summary = {**_valid_summary(), "summary": text}
        errors = validate_agent_review_summary_contract(summary, packet=PACKET)
        assert errors, text


def test_agent_review_summary_validator_rejects_unknown_lost_units() -> None:
    summary = {
        **_valid_summary(),
        "role_summaries": [
            {
                **_valid_summary()["role_summaries"][0],
                "quote": "약 1,200개 생산 손실이 예상됩니다.",
            }
        ],
    }

    errors = validate_agent_review_summary_contract(summary, packet=PACKET)

    assert "prose_lost_units_mismatch:약 1,200개 생산 손실" in errors


def test_agent_review_summary_validator_rejects_korean_priority_mismatch() -> None:
    packet = json.loads((GOLD_ROOT / "GS-004.json").read_text(encoding="utf-8"))
    summary = {
        **compose_deterministic_agent_review_summary(packet),
        "mode": "llm",
        "summary": "이 건은 우선순위가 낮아 다음 주에 확인해도 됩니다.",
    }

    errors = validate_agent_review_summary_contract(summary, packet=packet)

    assert "prose_priority_mismatch:low" in errors


def test_validated_agent_review_summary_discards_ungrounded_hold_candidate() -> None:
    packet = json.loads((GOLD_ROOT / "GS-007.json").read_text(encoding="utf-8"))
    bad_candidate = compose_deterministic_agent_review_summary(packet)
    bad_candidate.update(
        {
            "mode": "llm",
            "generated_at": "2099-01-01T00:00:00+09:00",
            "confidence_label": "grounded",
            "summary": "주축 베어링 마모가 확인되어 즉시 점검 후 교체가 필요합니다. 위험도 92%, 우선순위 immediate.",
            "evidence_gaps": [],
            "inspection_focus": [
                {
                    "component_id": "spindle_bearing",
                    "component_label": "주축 베어링",
                    "location_label": "가짜 위치",
                    "basis_refs": ["factor.1.invented_metric", "sop://made-up"],
                    "source_refs": packet["source_refs"],
                }
            ],
        }
    )

    errors = validate_agent_review_summary_contract(bad_candidate, packet=packet)
    assert "generated_at_mismatch" in errors
    assert "confidence_label_mismatch" in errors
    assert "inspection_focus_unavailable" in errors
    assert any(error.startswith("evidence_gaps_missing:") for error in errors)

    summary, fallback_errors = validated_agent_review_summary(
        packet=packet,
        candidate=bad_candidate,
    )
    assert fallback_errors == []
    assert summary["mode"] == "deterministic_fallback"
    assert summary["confidence_label"] == "data_quality_hold"
    assert summary["inspection_focus"] == []


def test_agent_review_summary_validator_rejects_unknown_component_and_basis_refs() -> None:
    summary = _valid_summary()
    summary["inspection_focus"] = [
        {
            **summary["inspection_focus"][0],
            "component_id": "unknown_component",
            "basis_refs": ["factor.1.invented_metric"],
        }
    ]

    errors = validate_agent_review_summary_contract(summary, packet=PACKET)

    assert "inspection_focus[0].component_id_unknown:unknown_component" in errors


def test_agent_review_summary_validator_rejects_basis_ref_outside_matching_target() -> None:
    summary = _valid_summary()
    summary["inspection_focus"] = [
        {
            **summary["inspection_focus"][0],
            "basis_refs": ["factor.99.invented_metric"],
        }
    ]

    errors = validate_agent_review_summary_contract(summary, packet=PACKET)

    assert "inspection_focus[0].basis_refs_unknown:factor.99.invented_metric" in errors


def test_agent_review_summary_validator_rejects_missing_packet_evidence_gap() -> None:
    summary = {**_valid_summary(), "evidence_gaps": PACKET["evidence_gaps"][:-1]}

    errors = validate_agent_review_summary_contract(summary, packet=PACKET)

    assert any(error.startswith("evidence_gaps_missing:") for error in errors)


def test_agent_review_summary_validator_rejects_unknown_evidence_gap() -> None:
    summary = {
        **_valid_summary(),
        "evidence_gaps": [
            *PACKET["evidence_gaps"],
            {
                "field": "invented_gap",
                "reason": "not_in_packet",
                "owner_domain": "diagnosis",
            },
        ],
    }

    errors = validate_agent_review_summary_contract(summary, packet=PACKET)

    assert "evidence_gaps_unknown:invented_gap|not_in_packet|diagnosis" in errors


def test_agent_review_summary_validator_rejects_missing_inspection_focus() -> None:
    summary = {**_valid_summary(), "inspection_focus": _valid_summary()["inspection_focus"][:1]}

    errors = validate_agent_review_summary_contract(summary, packet=PACKET)

    assert "inspection_focus_count_mismatch:1!=2" in errors


def test_agent_review_summary_validator_rejects_focus_ref_from_other_target() -> None:
    summary = _valid_summary()
    summary["inspection_focus"] = [
        {
            **summary["inspection_focus"][0],
            "source_refs": [PACKET["inspection_targets"][1]["source_ref"]],
        },
        summary["inspection_focus"][1],
    ]

    errors = validate_agent_review_summary_contract(summary, packet=PACKET)

    assert (
        "inspection_focus[0].source_refs_not_target_grounded:"
        + PACKET["inspection_targets"][1]["source_ref"]
        in errors
    )


def test_validated_agent_review_summary_discards_schema_invalid_candidate() -> None:
    bad_candidate = _valid_summary()
    del bad_candidate["title"]

    summary, errors = validated_agent_review_summary(
        packet=PACKET,
        candidate=bad_candidate,
    )

    assert errors == []
    assert summary["mode"] == "deterministic_fallback"
    assert summary["title"]


def test_validated_agent_review_summary_accepts_valid_candidate() -> None:
    candidate = _valid_summary()

    summary, errors = validated_agent_review_summary(packet=PACKET, candidate=candidate)

    assert errors == []
    assert summary == candidate


def test_agent_review_summary_schema_rejects_mutation_field() -> None:
    summary = {**_valid_summary(), "create_work_order": {"action_id": "WO-1"}}

    errors = list(Draft202012Validator(SUMMARY_SCHEMA).iter_errors(summary))
    assert errors
    assert any("Additional properties" in error.message for error in errors)
    assert "forbidden_fields:action_id,create_work_order" in validate_agent_review_summary(
        summary,
        packet=PACKET,
    )


def test_agent_review_summary_validator_rejects_unknown_source_ref() -> None:
    summary = {**_valid_summary(), "source_refs": ["unknown://source"]}

    assert validate_agent_review_summary(summary, packet=PACKET) == [
        "source_refs_unknown:unknown://source"
    ]


def test_agent_review_summary_validator_rejects_nested_unknown_source_ref() -> None:
    summary = _valid_summary()
    summary["inspection_focus"] = [
        {**summary["inspection_focus"][0], "source_refs": ["unknown://nested"]},
        summary["inspection_focus"][1],
    ]

    assert "source_refs_unknown:unknown://nested" in validate_agent_review_summary(
        summary,
        packet=PACKET,
    )


def test_agent_review_summary_validator_rejects_missing_source_ref() -> None:
    summary = {**_valid_summary(), "source_refs": []}

    schema_errors = list(Draft202012Validator(SUMMARY_SCHEMA).iter_errors(summary))
    assert schema_errors
    assert validate_agent_review_summary(summary, packet=PACKET) == ["source_refs_missing"]


def test_agent_review_summary_validator_rejects_forbidden_claims() -> None:
    summary = {
        **_valid_summary(),
        "summary": "SOP가 자동 정비 승인 기준이며 정비로 downtime 절감 효과가 입증됐습니다.",
    }

    errors = validate_agent_review_summary(summary, packet=PACKET)
    assert "forbidden_claims:SOP가 자동 정비 승인,정비로 downtime 절감" in errors


def test_agent_review_summary_validator_rejects_packet_mismatch() -> None:
    summary = {**_valid_summary(), "asset_id": "CNC-OTHER"}

    assert validate_agent_review_summary(summary, packet=PACKET) == ["asset_id_mismatch"]


def test_agent_review_packet_schema_rejects_empty_source_refs() -> None:
    packet = json.loads((GOLD_ROOT / "GS-007.json").read_text(encoding="utf-8"))
    packet["source_refs"] = []

    errors = list(Draft202012Validator(PACKET_SCHEMA).iter_errors(packet))

    assert errors
