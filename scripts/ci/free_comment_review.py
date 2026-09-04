#!/usr/bin/env python3
"""Run a zero-token-cost technical-comment review with a conservative quality gate.

The primary answer comes from Gemini 3.5 Flash-Lite on the Gemini Developer API
Free Tier. Gemma 4 26B A4B independently checks whether the draft is sufficiently
grounded to publish. Any API/quota/format/verifier failure exits non-zero so the
GitHub workflow can fall back to the existing Vertex Gemini 3.7 Flash reviewer.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    from scripts.ci.ai_review import comment_marker
except ModuleNotFoundError:  # Direct execution: python scripts/ci/free_comment_review.py
    from ai_review import comment_marker


PRIMARY_MODEL = "gemini-3.5-flash-lite"
PRIMARY_DISPLAY = "Gemini 3.5 Flash-Lite"
VERIFIER_MODEL = "gemma-4-26b-a4b-it"
VERIFIER_DISPLAY = "Gemma 4 26B A4B"
API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"


def _request(
    model: str,
    api_key: str,
    payload: dict[str, Any],
    *,
    retry_quota: bool = True,
) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{API_ROOT}/{model}:generateContent",
        data=data,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )
    last_error = "unknown error"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:500]
            last_error = f"HTTP {exc.code}: {body}"
            if exc.code == 429 and not retry_quota:
                break
            if exc.code not in {429, 500, 502, 503, 504}:
                break
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = str(exc)
        time.sleep(2**attempt)
    raise RuntimeError(last_error)


def _visible_text(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if payload.get("error"):
        raise RuntimeError(json.dumps(payload["error"], ensure_ascii=False)[:500])
    candidates = payload.get("candidates") or []
    if not candidates:
        raise RuntimeError("model returned no candidates")
    candidate = candidates[0]
    if candidate.get("finishReason") != "STOP":
        raise RuntimeError(
            f"model response incomplete: finishReason={candidate.get('finishReason')!r}"
        )
    parts = candidate.get("content", {}).get("parts", [])
    text = "\n".join(
        str(part.get("text") or "")
        for part in parts
        if part.get("text") and not part.get("thought")
    ).strip()
    if not text:
        raise RuntimeError("model returned no visible text")
    return text, dict(payload.get("usageMetadata") or {})


def _draft_is_well_formed(text: str) -> bool:
    verdicts = (
        "타당",
        "부분적으로 타당",
        "재현되지 않음",
        "방향은 타당하지만 해결책은 과도함",
        "현재 head에서 이미 해결됨",
    )
    return 80 <= len(text) <= 18_000 and any(verdict in text[:1200] for verdict in verdicts)


def _section(text: str, start: str, end: str | None = None) -> str:
    marker = f"\n{start}\n"
    index = text.find(marker)
    if index < 0:
        return ""
    body_start = index + len(marker)
    if end is None:
        return text[body_start:]
    end_marker = f"\n{end}\n"
    end_index = text.find(end_marker, body_start)
    return text[body_start:] if end_index < 0 else text[body_start:end_index]


def _compact_verifier_evidence(source_prompt: str) -> str:
    """Build a verifier-only fact bundle that stays well below Gemma free TPM.

    The primary reviewer can still see the richer prompt. Gemma is only a
    publication gate, so it gets the source comment, deterministic metadata,
    risk hints, a small trusted-contract excerpt and focused changed-code
    evidence. This avoids spending Gemma's comparatively small free input-token
    allowance on a second copy of the entire review prompt.
    """

    chunks = [
        ("SOURCE", _section(source_prompt, "SOURCE", "PR"), 5_000),
        ("PR", _section(source_prompt, "PR", "INTENT_RISK_HINTS (verify before relying on them)"), 3_000),
        (
            "INTENT_RISK_HINTS",
            _section(
                source_prompt,
                "INTENT_RISK_HINTS (verify before relying on them)",
                "TRUSTED_BASE_CONTEXT",
            ),
            2_500,
        ),
        ("TRUSTED_BASE_CONTEXT", _section(source_prompt, "TRUSTED_BASE_CONTEXT", "CHANGED_FILES"), 4_000),
        ("CHANGED_FILES", _section(source_prompt, "CHANGED_FILES", "CHANGED_HEAD_SOURCE_CONTEXT"), 3_500),
        (
            "CHANGED_HEAD_SOURCE_CONTEXT",
            _section(source_prompt, "CHANGED_HEAD_SOURCE_CONTEXT", "DIFF"),
            7_000,
        ),
        ("DIFF", _section(source_prompt, "DIFF"), 7_000),
    ]
    blocks: list[str] = []
    for label, content, limit in chunks:
        content = content.strip()
        if content:
            blocks.append(f"===== {label} =====\n{content[:limit]}")
    evidence = "\n\n".join(blocks)
    # Final hard guard. About 28k chars plus the candidate/instructions remains
    # well below the 16k-token/min Gemma free-tier ceiling observed in CI.
    return evidence[:28_000]


def _verifier_prompt(source_prompt: str, draft: str) -> str:
    evidence = _compact_verifier_evidence(source_prompt)
    return f"""You are an independent quality gate for an automated pull-request technical-comment response.

The candidate response was drafted by another model. Do not rewrite it. Decide only whether it is safe to publish without a stronger reasoning-model fallback.

ACCEPT only when all are true:
- the verdict is supported by the supplied repository evidence;
- it does not simply agree with the human comment;
- cited paths/symbols and implementation advice are consistent with the evidence;
- it does not invent repository facts, tests, approvals, or runtime state;
- it respects the trust boundary and does not expose/request secrets;
- no substantial architecture/domain/security/migration ambiguity requires deeper reasoning.

Otherwise ESCALATE. Be conservative when evidence is truncated or conflicting.

Return JSON only:
{{"decision":"ACCEPT|ESCALATE","confidence":0.0,"reason":"short reason"}}

REVIEW EVIDENCE AND POLICY
{evidence}

CANDIDATE RESPONSE
{draft[:8_000]}
"""


def _parse_verifier(text: str) -> tuple[str, float, str]:
    candidate = text.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start < 0 or end <= start:
            raise RuntimeError("Gemma verifier did not return JSON")
        payload = json.loads(candidate[start : end + 1])
    decision = str(payload.get("decision") or "").upper()
    try:
        confidence = float(payload.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    reason = str(payload.get("reason") or "")[:500]
    return decision, confidence, reason


def run(args: argparse.Namespace) -> None:
    api_key = os.getenv("GEMINI_FREE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("GEMINI_FREE_API_KEY is not configured; use Vertex fallback")

    prompt = Path(args.prompt).read_text(encoding="utf-8")
    primary_payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 3500,
        },
    }
    try:
        primary_raw = _request(PRIMARY_MODEL, api_key, primary_payload)
        draft, primary_usage = _visible_text(primary_raw)
        if not _draft_is_well_formed(draft):
            raise RuntimeError("Flash-Lite draft failed deterministic format checks")

        verifier_payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": _verifier_prompt(prompt, draft)}],
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
                # This second model is a binary quality gate, not the primary
                # reviewer. Gemma 4 supports MINIMAL thinking for this kind of
                # classification, which avoids spending its output allowance
                # on long internal reasoning before the JSON verdict.
                "maxOutputTokens": 600,
                "thinkingConfig": {"thinkingLevel": "MINIMAL"},
            },
        }
        verifier_prompt = _verifier_prompt(prompt, draft)
        verifier_payload["contents"][0]["parts"][0]["text"] = verifier_prompt
        verifier_raw = _request(
            VERIFIER_MODEL,
            api_key,
            verifier_payload,
            retry_quota=False,
        )
        verifier_text, verifier_usage = _visible_text(verifier_raw)
        decision, confidence, reason = _parse_verifier(verifier_text)
        if decision != "ACCEPT" or confidence < 0.70:
            raise RuntimeError(
                f"Gemma verifier requested stronger review: decision={decision} "
                f"confidence={confidence:.2f} reason={reason}"
            )
    except Exception as exc:
        # This message intentionally contains no key/request URL. The workflow
        # treats any failure as a signal to use the existing paid reasoning path.
        raise SystemExit(f"free review not publishable; use Vertex fallback: {exc}")

    marker = comment_marker(args.source_kind, args.source_id, args.head_sha)
    body = (
        f"{marker}\n"
        f"## {PRIMARY_DISPLAY} 팀 코멘트 검토\n\n"
        f"무료 라우팅: Gemini Developer API Free Tier · `{PRIMARY_MODEL}`  \n"
        f"품질 게이트: `{VERIFIER_MODEL}` ({VERIFIER_DISPLAY}) 독립 검증 통과  \n"
        "불확실/고위험/무료 API 실패 시 기존 Vertex Gemini 3.7 Flash 경로로 자동 승격됩니다.  \n\n"
        f"{draft.strip()}\n"
    )
    Path(args.output).write_text(body, encoding="utf-8")
    print(
        "free review accepted:",
        f"primary_prompt={primary_usage.get('promptTokenCount')}",
        f"primary_output={primary_usage.get('candidatesTokenCount')}",
        f"verifier_chars={len(verifier_prompt)}",
        f"verifier_prompt={verifier_usage.get('promptTokenCount')}",
        f"verifier_output={verifier_usage.get('candidatesTokenCount')}",
        f"verifier_confidence={confidence:.2f}",
    )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    root.add_argument("--prompt", required=True)
    root.add_argument("--source-kind", required=True)
    root.add_argument("--source-id", required=True)
    root.add_argument("--head-sha", required=True)
    root.add_argument("--output", required=True)
    return root


if __name__ == "__main__":
    run(parser().parse_args())
