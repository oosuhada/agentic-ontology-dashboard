import json
import unittest
from argparse import Namespace
from pathlib import Path

from scripts.ci.ai_review import (
    DEFAULT_CONTEXT_ROUTING,
    build_verified_evidence,
    classify_comment,
    comment_requires_reasoning,
    compact_local_review_prompt,
    context_documents,
    detect_intent_risk_hints,
    event_to_comment,
    human_technical_feedback,
    idempotency_decision,
    is_trusted_comment_author,
    local_review_requires_vertex,
    review_profile,
    review_force_vertex,
    route_context,
    should_run_full_review,
)
from scripts.ci.free_comment_review import _compact_verifier_evidence, _verifier_prompt
from scripts.ci.free_comment_review import _draft_is_well_formed, _parse_verifier
from scripts.ci.free_review_falsifier import (
    _normalize_scope_escalation,
    compact_candidate,
    compact_evidence,
    verifier_prompt,
)


class AiReviewAutomationTests(unittest.TestCase):
    def test_local_review_prompt_stays_within_qwen_runtime_budget(self):
        prompt = """review policy

SOURCE
comment=""" + ("technical question " * 2000) + """

PR
number=72

INTENT_RISK_HINTS (verify before relying on them)
["domain"]

TRUSTED_BASE_CONTEXT
""" + ("contract evidence " * 5000) + """

CHANGED_FILES
M\tsystems/backend/app/dashboard/dashboard_service.py

CHANGED_HEAD_SOURCE_CONTEXT
""" + ("head source " * 8000) + """

DIFF
""" + ("+changed line\n" * 12000)

        compact = compact_local_review_prompt(prompt, "comment")
        self.assertLessEqual(len(compact), 89_000)
        self.assertIn("SOURCE", compact)
        self.assertIn("TRUSTED_BASE_CONTEXT", compact)
        self.assertIn("CHANGED_HEAD_SOURCE_CONTEXT", compact)

    def test_full_review_risk_gate_keeps_privileged_paths_on_vertex_final(self):
        force, reason = review_force_vertex([".github/workflows/code-review.yml"])
        self.assertTrue(force)
        self.assertIn("trust-boundary", reason)

        force, reason = review_force_vertex(
            ["systems/backend/app/dashboard/dashboard_service.py"]
        )
        self.assertFalse(force)
        self.assertIn("local semantic", reason)

        force, reason = review_force_vertex(
            ["systems/frontend/src/features/operations/operations/OperationsOperationsPage.tsx"],
            explicit=True,
        )
        self.assertTrue(force)
        self.assertIn("explicit", reason)

    def test_full_review_risk_gate_does_not_escalate_on_volume_or_generic_infra(self):
        routine_paths = [
            f"systems/backend/app/dashboard/generated_{index}.py"
            for index in range(80)
        ]
        force, reason = review_force_vertex(routine_paths)
        self.assertFalse(force)
        self.assertIn("change volume alone", reason)

        force, _reason = review_force_vertex(
            ["systems/backend/app/infra/db/dashboard_repository.py"]
        )
        self.assertFalse(force)

    def test_full_review_risk_gate_keeps_true_trust_and_migration_semantics_on_vertex(self):
        for path in (
            ".github/workflows/architecture.yml",
            "systems/backend/app/auth/auth_service.py",
            "systems/backend/migrations/postgresql/0031_runtime.sql",
            "systems/backend/ontology_dashboard/migrations.py",
            "scripts/check_postgresql_migration.py",
            "scripts/migrate_database.py",
            "systems/verify_architecture.py",
        ):
            with self.subTest(path=path):
                force, _reason = review_force_vertex([path])
                self.assertTrue(force)

    def test_review_workflows_use_latest_head_wins_queue_guards(self):
        repository_root = Path(__file__).resolve().parents[1]
        architecture = (repository_root / ".github/workflows/architecture.yml").read_text(
            encoding="utf-8"
        )
        full_review = (repository_root / ".github/workflows/code-review.yml").read_text(
            encoding="utf-8"
        )
        comment_review = (
            repository_root / ".github/workflows/pr-comment-review.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("group: architecture-${{ github.ref }}", architecture)
        self.assertIn("cancel-in-progress: true", architecture)
        self.assertIn("name: Publish release marker", architecture)
        self.assertNotIn("\n  review:\n", architecture)

        self.assertIn("name: Claim latest-head review slot", full_review)
        self.assertIn("stale review discarded before model spend", full_review)
        self.assertIn("PR advanced before Vertex spend", full_review)
        self.assertIn("stale completed review discarded before publish", full_review)
        self.assertIn("steps.freshness.outputs.current == 'true'", full_review)

        self.assertIn("stale comment review discarded before model spend", comment_review)
        self.assertIn("PR advanced before Vertex spend", comment_review)
        self.assertIn("stale completed response discarded before publish", comment_review)

    def test_local_review_output_escalates_blockers_but_not_clean_reviews(self):
        force, reason = local_review_requires_vertex(
            "### 발견 사항\n[P1] domain boundary violation\n\n### Merge Readiness\nNot Ready",
            "pr",
        )
        self.assertTrue(force)
        self.assertIn("P0/P1", reason)

        force, reason = local_review_requires_vertex(
            "### 발견 사항\n현재 actionable finding은 없습니다.\n\n### Merge Readiness\nReady to Merge",
            "pr",
        )
        self.assertFalse(force)
        self.assertIn("no high-consequence", reason)

        force, reason = local_review_requires_vertex(
            "@reviewer 부분적으로 타당합니다. [P1] 인증 권한 경계 문제가 확인됩니다.",
            "comment",
        )
        self.assertTrue(force)
        self.assertIn("P0/P1", reason)

    def test_gemma_falsifier_packet_is_smaller_than_local_prompt(self):
        source = """policy

SOURCE
comment=""" + ("human comment " * 1000) + """

PR
number=72

INTENT_RISK_HINTS (verify before relying on them)
["domain"]

TRUSTED_BASE_CONTEXT
""" + ("contract " * 5000) + """

CHANGED_FILES
M\tsystems/backend/app/dashboard/dashboard_service.py

CHANGED_HEAD_SOURCE_CONTEXT
""" + ("source " * 10000) + """

DIFF
""" + ("+line\n" * 15000)
        packet = compact_evidence(source, "comment")
        candidate = compact_candidate("타당합니다. " + ("근거 설명 " * 3000), "comment")
        self.assertLessEqual(len(packet), 23_000)
        self.assertLessEqual(len(candidate), 8_100)
        self.assertIn("CHANGED_HEAD_SOURCE_CONTEXT", packet)

    def test_gemma_falsifier_preserves_demo_vs_production_scope_evidence(self):
        source = """policy

VERIFIED_EVIDENCE
architecture=success

INTENT_RISK_HINTS (deterministic hints, verify against the diff before using)
["fixture fallback"]

HUMAN_TECHNICAL_FEEDBACK
none

TRUSTED_BASE_CONTEXT
Production runtime is app.main:app.

PR_TITLE (untrusted)
canonical convergence

CHANGED_FILES
M\tsystems/backend/app/diagnosis/evidence.py
M\tsystems/backend/app/operations/service.py

ARCHITECTURE_JOB_LOG (untrusted execution output; consult mainly on failure)
green

CHANGED_HEAD_SOURCE_CONTEXT (untrusted changed source; prioritized before truncated diff)
systems/backend/app/diagnosis/evidence.py
class FixtureContextProvider:
    pass
def build_evidence_package(fixture, context_provider=None):
    provider = context_provider or FixtureContextProvider()

""" + ("unrelated source\n" * 4000) + """
systems/backend/app/operations/service.py
\"\"\"Canonical manufacturing demonstration application service.\"\"\"
class ManufacturingPredictiveMaintenanceService:
    def _context_provider(self, fixture):
        return FixtureContextProvider()

DIFF (untrusted review input)
+demo compatibility refactor
"""
        prompt = verifier_prompt(
            source,
            "### 발견 사항\n현재 actionable finding은 없습니다.\n\n### Merge Readiness\nReady to Merge",
            "pr",
        )
        self.assertIn("RUNTIME_SCOPE_EVIDENCE", prompt)
        self.assertIn("Canonical manufacturing demonstration application service", prompt)
        self.assertIn("production/deployment caller or entrypoint", prompt)
        self.assertIn("Operations/demo/test", prompt)
        self.assertIn("legacy names, not runtime", prompt)
        self.assertIn("variable name", prompt)
        self.assertIn("File/module placement is also not caller evidence", prompt)
        self.assertIn("hypothetical reachability", prompt)

    def test_gemma_fixture_escalation_requires_concrete_runtime_caller(self):
        decision, confidence, reason = _normalize_scope_escalation(
            "ESCALATE",
            1.0,
            "FixtureContextProvider in systems/backend/app/diagnosis/evidence.py reads a fixture file.",
            source_prompt="""

TRUSTED_BASE_CONTEXT
ManufacturingPredictiveMaintenanceService is the Operations/demo compatibility application service.

PR_TITLE (untrusted)
x

CHANGED_FILES
M\tsystems/backend/app/operations/service.py

ARCHITECTURE_JOB_LOG (untrusted execution output; consult mainly on failure)
green

CHANGED_HEAD_SOURCE_CONTEXT (untrusted changed source; prioritized before truncated diff)
\"\"\"Canonical manufacturing demonstration application service.\"\"\"

DIFF (untrusted review input)
x
""",
            kind="pr",
        )
        self.assertEqual(decision, "ACCEPT")
        self.assertGreaterEqual(confidence, 0.85)
        self.assertIn("without a concrete production caller", reason)

        decision, confidence, reason = _normalize_scope_escalation(
            "ESCALATE",
            0.98,
            "systems/backend/app/operations/router.py production caller reaches FixtureContextProvider via the service.",
            source_prompt="""

TRUSTED_BASE_CONTEXT
ManufacturingPredictiveMaintenanceService is the Operations/demo compatibility application service.

PR_TITLE (untrusted)
x

CHANGED_FILES
M\tsystems/backend/app/operations/router.py

ARCHITECTURE_JOB_LOG (untrusted execution output; consult mainly on failure)
green

CHANGED_HEAD_SOURCE_CONTEXT (untrusted changed source; prioritized before truncated diff)
\"\"\"Canonical manufacturing demonstration application service.\"\"\"

DIFF (untrusted review input)
x
""",
            kind="pr",
        )
        self.assertEqual(decision, "ESCALATE")
        self.assertEqual(confidence, 0.98)
        self.assertIn("router.py", reason)

        decision, _confidence, _reason = _normalize_scope_escalation(
            "ESCALATE",
            0.97,
            "FixtureContextProvider reads a local fixture file.",
            source_prompt="""

TRUSTED_BASE_CONTEXT
Production diagnosis service.

PR_TITLE (untrusted)
x

CHANGED_FILES
M\tsystems/backend/app/diagnosis/evidence.py

ARCHITECTURE_JOB_LOG (untrusted execution output; consult mainly on failure)
green

CHANGED_HEAD_SOURCE_CONTEXT (untrusted changed source; prioritized before truncated diff)
class FixtureContextProvider: pass

DIFF (untrusted review input)
x
""",
            kind="pr",
        )
        self.assertEqual(decision, "ESCALATE")

        decision, confidence, reason = _normalize_scope_escalation(
            "ESCALATE",
            0.7,
            "Fixture provider is returned by get_provider used in the deployed API.",
            source_prompt="""

TRUSTED_BASE_CONTEXT
Production diagnosis service.

PR_TITLE (untrusted)
x

CHANGED_FILES
M\tsystems/backend/app/diagnosis/evidence.py

ARCHITECTURE_JOB_LOG (untrusted execution output; consult mainly on failure)
green

CHANGED_HEAD_SOURCE_CONTEXT (untrusted changed source; prioritized before truncated diff)
# demo compatibility boundary: fixture provider retained for Operations

DIFF (untrusted review input)
+ # demo compatibility boundary: fixture provider retained for Operations
""",
            kind="pr",
        )
        self.assertEqual(decision, "ESCALATE")
        self.assertEqual(confidence, 0.7)
        self.assertIn("deployed API", reason)

        decision, confidence, reason = _normalize_scope_escalation(
            "ESCALATE",
            0.96,
            "The fixture fallback is wired through ontology_dashboard/dependencies.py and reached on every deployed request.",
            source_prompt="""

TRUSTED_BASE_CONTEXT
ManufacturingPredictiveMaintenanceService is the Operations/demo compatibility application service.

PR_TITLE (untrusted)
x

CHANGED_FILES
M\tsystems/backend/ontology_dashboard/dependencies.py

ARCHITECTURE_JOB_LOG (untrusted execution output; consult mainly on failure)
green

CHANGED_HEAD_SOURCE_CONTEXT (untrusted changed source; prioritized before truncated diff)
x

DIFF (untrusted review input)
x
""",
            kind="pr",
        )
        self.assertEqual(decision, "ESCALATE")
        self.assertEqual(confidence, 0.96)
        self.assertIn("dependencies.py", reason)

    def test_free_verifier_context_is_compact_even_for_large_review_prompt(self):
        prompt = """header

SOURCE
comment=""" + ("human technical comment " * 500) + """

PR
number=72
title=architecture migration

INTENT_RISK_HINTS (verify before relying on them)
["architecture"]

TRUSTED_BASE_CONTEXT
""" + ("trusted contract " * 3000) + """

CHANGED_FILES
M\tsystems/backend/app/main.py

CHANGED_HEAD_SOURCE_CONTEXT
""" + ("source code " * 5000) + """

DIFF
""" + ("+changed line\n" * 8000)

        compact = _compact_verifier_evidence(prompt)
        verifier = _verifier_prompt(prompt, "타당 — repository evidence와 일치합니다.")

        self.assertLessEqual(len(compact), 28_000)
        self.assertLess(len(verifier), 40_000)
        self.assertIn("SOURCE", compact)
        self.assertIn("CHANGED_FILES", compact)
        self.assertIn("DIFF", compact)

    def test_context_router_selects_backend_and_domain_docs(self):
        categories = route_context(
            ["systems/backend/ontology_dashboard/closed_loop/domain.py"]
        )
        self.assertIn("project_intent", categories)
        self.assertIn("architecture", categories)
        self.assertIn("closed_loop", categories)

    def test_context_router_selects_maintenance_as_closed_loop(self):
        categories = route_context(
            ["systems/backend/app/maintenance/maintenance_service.py"]
        )
        self.assertIn("architecture", categories)
        self.assertIn("closed_loop", categories)

    def test_context_router_selects_frontend_operations_operations_docs(self):
        categories = route_context(
            ["systems/frontend/src/features/operations/operations/OperationsOperationsPage.tsx"]
        )
        self.assertIn("project_intent", categories)
        self.assertIn("architecture", categories)
        self.assertIn("operations", categories)
        self.assertIn("frontend_operations", categories)

    def test_context_router_selects_deployment_docs_for_dockerignore(self):
        categories = route_context([".dockerignore"])
        self.assertIn("project_intent", categories)
        self.assertIn("deployment", categories)

    def test_context_router_uses_current_operations_paths_and_closed_loop_product_contract(self):
        categories = route_context(
            ["systems/frontend/src/features/operations/operations/OperationsOperationsPage.tsx"]
        )
        paths = context_documents(categories, DEFAULT_CONTEXT_ROUTING)
        self.assertIn("docs/operations/current-operations-implementation-baseline.md", paths)
        self.assertIn("docs/operations/functional-specification.md", paths)
        self.assertIn("docs/closed-loop-product-consumption-contract.md", paths)
        self.assertIn("docs/closed-loop-runtime-overlay-contract.md", paths)
        self.assertNotIn(
            "docs/operations/history/2026-08-week2/frontend-implementation-import.md", paths
        )

    def test_architecture_context_includes_backend_migration_map(self):
        categories = route_context(["docs/backend-migration-map.md"])
        self.assertIn("architecture", categories)
        paths = context_documents(categories, DEFAULT_CONTEXT_ROUTING)
        self.assertIn("docs/backend-migration-map.md", paths)

    def test_closed_loop_context_includes_product_api_ui_consumption_contract(self):
        categories = route_context(
            ["systems/backend/ontology_dashboard/closed_loop/domain.py"]
        )
        paths = context_documents(categories, DEFAULT_CONTEXT_ROUTING)
        self.assertIn("docs/closed-loop-domain-contract.md", paths)
        self.assertIn("docs/closed-loop-product-consumption-contract.md", paths)
        self.assertIn("docs/closed-loop-runtime-overlay-contract.md", paths)

    def test_declared_context_paths_exist_and_old_namespace_is_absent(self):
        repository_root = Path(__file__).resolve().parents[1]
        routing_file = repository_root / "docs/ai-code-review-context.json"
        declared = json.loads(routing_file.read_text(encoding="utf-8"))["routing"]
        old_namespace = "docs/" + "mentoring-operations-2026-08"

        for routing_name, routing in (
            ("json", declared),
            ("fallback", DEFAULT_CONTEXT_ROUTING),
        ):
            for category, rule in routing.items():
                for path in rule.get("context", []):
                    with self.subTest(
                        routing=routing_name, category=category, path=path
                    ):
                        self.assertNotIn(old_namespace, path)
                        self.assertTrue((repository_root / path).is_file(), path)

        self.assertEqual(declared, DEFAULT_CONTEXT_ROUTING)

    def test_default_routing_does_not_use_week2_history_as_current_contract(self):
        history_prefix = "docs/operations/history/2026-08-week2/"
        for category, rule in DEFAULT_CONTEXT_ROUTING.items():
            for path in rule.get("context", []):
                with self.subTest(category=category, path=path):
                    self.assertFalse(path.startswith(history_prefix), path)

    def test_project_intent_hint_detects_frontend_state_machine_reimplementation(self):
        diff = """diff --git a/x b/x
+++ b/x
+if (workOrder.status === \"approved\") actions.push(\"start\")
"""
        hints = detect_intent_risk_hints(
            diff, ["systems/frontend/src/features/operations/operations/OperationsOperationsPage.tsx"]
        )
        self.assertTrue(any("state machine" in hint for hint in hints))

    def test_project_intent_hint_detects_frontend_generated_persisted_id(self):
        diff = """diff --git a/x b/x
+++ b/x
+const id = `${projectId}-${eventId}-${Date.now()}`
"""
        hints = detect_intent_risk_hints(
            diff, ["systems/frontend/src/features/operations/operations/OperationsOperationsPage.tsx"]
        )
        self.assertTrue(any("identifiers" in hint for hint in hints))

    def test_project_intent_hint_detects_demo_fixture_hardcoding(self):
        diff = """diff --git a/x b/x
+++ b/x
+if (projectId === \"manufacturing-demo-project\") return fixture
"""
        hints = detect_intent_risk_hints(
            diff,
            ["systems/backend/ontology_dashboard/predictive_maintenance_runtime/service.py"],
        )
        self.assertTrue(any("fixture-specific" in hint for hint in hints))

    def test_comment_classifier_examples(self):
        self.assertEqual(
            classify_comment("[P2] .dockerignore가 classifier에서 빠집니다"),
            "actionable_review",
        )
        self.assertEqual(
            classify_comment("이 방식 대신 server available_actions를 쓰는 게 맞지 않나요?"),
            "technical_question",
        )
        self.assertEqual(classify_comment("approve 입니다"), "approval")
        self.assertEqual(classify_comment("확인했습니다"), "acknowledgement")
        self.assertEqual(classify_comment("감사합니다"), "acknowledgement")
        self.assertEqual(classify_comment("/ai-review"), "full_review_request")

    def test_comment_route_keeps_decisive_formal_reviews_on_reasoning_model(self):
        for state in ("APPROVED", "CHANGES_REQUESTED"):
            with self.subTest(state=state):
                reasoning, reason = comment_requires_reasoning(
                    {"review": {"state": state}}
                )
                self.assertTrue(reasoning)
                self.assertIn(state, reason)

        reasoning, reason = comment_requires_reasoning(
            {"comment": {"body": "[P2] implementation detail needs a fix"}}
        )
        self.assertFalse(reasoning)
        self.assertIn("ordinary technical", reason)

        reasoning, reason = comment_requires_reasoning(
            {"comment": {"body": "[P1] OIDC 권한 경계가 fail-open입니다"}}
        )
        self.assertTrue(reasoning)
        self.assertIn("P0/P1", reason)

        reasoning, reason = comment_requires_reasoning(
            {
                "comment": {
                    "body": "이 부분은 P2 수준이지만 workflow 변경입니다",
                    "path": ".github/workflows/code-review.yml",
                }
            }
        )
        self.assertTrue(reasoning)
        self.assertIn("workflow", reason)

    def test_free_comment_quality_gate_requires_verdict_and_accept_json(self):
        self.assertTrue(
            _draft_is_well_formed(
                "@reviewer 부분적으로 타당합니다. "
                "현재 구현 근거를 확인하면 수정 범위는 해당 helper로 제한됩니다. "
                "권장 구현과 회귀 검증을 함께 적용하는 것이 안전합니다."
            )
        )
        self.assertFalse(_draft_is_well_formed("looks good"))

        decision, confidence, reason = _parse_verifier(
            '{"decision":"ACCEPT","confidence":0.92,"reason":"grounded"}'
        )
        self.assertEqual(decision, "ACCEPT")
        self.assertAlmostEqual(confidence, 0.92)
        self.assertEqual(reason, "grounded")

        fenced = "```json\n{\"decision\":\"ESCALATE\",\"confidence\":0.8,\"reason\":\"ambiguous\"}\n```"
        decision, confidence, _ = _parse_verifier(fenced)
        self.assertEqual(decision, "ESCALATE")
        self.assertAlmostEqual(confidence, 0.8)

    def test_review_profile_routes_docs_to_flash_lite_and_code_to_reasoning(self):
        docs = review_profile(["docs/architecture.md"])
        code = review_profile(["systems/backend/app/main.py"])
        self.assertEqual(docs["model_id"], "gemini-3.5-flash-lite")
        self.assertEqual(docs["max_output_tokens"], 4000)
        self.assertEqual(code["model_id"], "gemini-3.7-flash")
        self.assertEqual(code["max_output_tokens"], 6000)

    def test_docs_only_review_skips_unless_explicit(self):
        paths = ["docs/architecture.md", "README.md"]
        run, reason = should_run_full_review("HEAD", "HEAD", paths)
        self.assertFalse(run)
        self.assertIn("documentation-only", reason)
        run, reason = should_run_full_review("HEAD", "HEAD", paths, explicit=True)
        self.assertTrue(run)
        self.assertIn("explicit", reason)

    def test_comment_event_ignores_automated_marker_and_bot_loop(self):
        event = {
            "action": "created",
            "issue": {"number": 44, "pull_request": {"url": "x"}},
            "comment": {
                "id": 123,
                "body": "<!-- automated-comment-review source-kind=issue_comment source-comment-id=1 head-sha=abc -->\n[P2] test",
                "author_association": "MEMBER",
                "user": {"login": "github-actions[bot]", "type": "Bot"},
            },
        }
        info = event_to_comment(event)
        self.assertFalse(info.eligible)

    def test_trusted_comment_author_associations_are_explicit(self):
        for association in ("OWNER", "MEMBER", "COLLABORATOR"):
            with self.subTest(association=association):
                self.assertTrue(is_trusted_comment_author(association))

        for association in ("NONE", "CONTRIBUTOR", "FIRST_TIME_CONTRIBUTOR", ""):
            with self.subTest(association=association):
                self.assertFalse(is_trusted_comment_author(association))

    def test_member_technical_comment_can_enter_credentialed_review(self):
        event = {
            "action": "created",
            "issue": {"number": 43, "pull_request": {"url": "x"}},
            "comment": {
                "id": 201,
                "body": "[P1] OIDC gate 오류를 수정해야 합니다",
                "author_association": "MEMBER",
                "user": {"login": "KOR-GANG", "type": "User"},
            },
        }
        info = event_to_comment(event)
        self.assertTrue(info.authorized)
        self.assertTrue(info.eligible)

    def test_member_ai_review_command_can_enter_repo_gate_without_comment_vertex_review(self):
        event = {
            "action": "created",
            "issue": {"number": 43, "pull_request": {"url": "x"}},
            "comment": {
                "id": 203,
                "body": "/ai-review",
                "author_association": "MEMBER",
                "user": {"login": "KOR-GANG", "type": "User"},
            },
        }
        info = event_to_comment(event)
        self.assertEqual(info.classification, "full_review_request")
        self.assertTrue(info.authorized)
        self.assertTrue(info.eligible)

    def test_member_request_changes_review_uses_authoritative_rest_metadata(self):
        event = {
            "action": "submitted",
            "pull_request": {"number": 23},
            "review": {
                "id": 4959998844,
                "body": "[P1] canonical contract blocker가 남아 있습니다",
                "state": "changes_requested",
                # pull_request_review webhook payloads must not be trusted to
                # carry the association used by the credential gate.
                "user": {"login": "oosuhada", "type": "User"},
            },
        }
        authoritative_review = {
            "id": 4959998844,
            "body": "[P1] canonical contract blocker가 남아 있습니다",
            "state": "CHANGES_REQUESTED",
            "author_association": "MEMBER",
            "user": {"login": "oosuhada", "type": "User"},
        }

        webhook_only = event_to_comment(event)
        self.assertEqual(webhook_only.classification, "actionable_review")
        self.assertFalse(webhook_only.authorized)
        self.assertFalse(webhook_only.eligible)

        hydrated = event_to_comment(event, authoritative_review=authoritative_review)
        self.assertEqual(hydrated.source_kind, "review")
        self.assertEqual(hydrated.source_id, "4959998844")
        self.assertEqual(hydrated.author_association, "MEMBER")
        self.assertEqual(hydrated.classification, "actionable_review")
        self.assertTrue(hydrated.authorized)
        self.assertTrue(hydrated.eligible)

    def test_external_request_changes_review_remains_blocked_after_hydration(self):
        event = {
            "action": "submitted",
            "pull_request": {"number": 23},
            "review": {
                "id": 99,
                "body": "[P1] 버그가 있습니다",
                "state": "changes_requested",
                "user": {"login": "external-user", "type": "User"},
            },
        }
        authoritative_review = {
            "id": 99,
            "body": "[P1] 버그가 있습니다",
            "state": "CHANGES_REQUESTED",
            "author_association": "NONE",
            "user": {"login": "external-user", "type": "User"},
        }

        info = event_to_comment(event, authoritative_review=authoritative_review)
        self.assertEqual(info.classification, "actionable_review")
        self.assertFalse(info.authorized)
        self.assertFalse(info.eligible)

    def test_external_technical_comment_is_classified_but_cannot_enter_oidc_job(self):
        event = {
            "action": "created",
            "issue": {"number": 43, "pull_request": {"url": "x"}},
            "comment": {
                "id": 202,
                "body": "[P1] 버그가 있습니다",
                "author_association": "NONE",
                "user": {"login": "external-user", "type": "User"},
            },
        }
        info = event_to_comment(event)
        self.assertEqual(info.classification, "actionable_review")
        self.assertFalse(info.authorized)
        self.assertFalse(info.eligible)

    def test_idempotency_noops_same_source_and_head(self):
        comments = [
            {
                "id": 77,
                "body": "<!-- automated-comment-review source-kind=issue_comment source-comment-id=123 head-sha=abc -->\nresponse",
            }
        ]
        self.assertEqual(
            idempotency_decision(comments, "issue_comment", "123", "abc"),
            ("noop", "77"),
        )

    def test_idempotency_updates_when_head_changes(self):
        comments = [
            {
                "id": 77,
                "body": "<!-- automated-comment-review source-kind=issue_comment source-comment-id=123 head-sha=abc -->\nresponse",
            }
        ]
        self.assertEqual(
            idempotency_decision(comments, "issue_comment", "123", "def"),
            ("update", "77"),
        )

    def test_feedback_filter_keeps_only_human_technical_feedback(self):
        feedback = human_technical_feedback(
            [
                {
                    "id": 1,
                    "body": "[P2] unknown path가 fail-open입니다",
                    "user": {"login": "KOR-GANG", "type": "User"},
                },
                {
                    "id": 2,
                    "body": "감사합니다",
                    "user": {"login": "teammate", "type": "User"},
                },
                {
                    "id": 3,
                    "body": "[P2] bot finding",
                    "user": {"login": "github-actions[bot]", "type": "Bot"},
                },
            ],
            [],
            [],
        )
        self.assertEqual(len(feedback), 1)
        self.assertEqual(feedback[0]["author"], "KOR-GANG")

    def test_required_false_is_na_not_missing_evidence(self):
        evidence = build_verified_evidence(
            Namespace(
                architecture_result="success",
                docker_required="false",
                docker_verified="false",
                frontend_required="false",
                frontend_verified="false",
                operations_required="false",
                operations_verified="false",
            )
        )
        self.assertEqual(evidence["missing_required"], [])
        self.assertEqual(evidence["merge_readiness_ceiling"], "Ready to Merge")

    def test_required_unverified_caps_readiness(self):
        evidence = build_verified_evidence(
            Namespace(
                architecture_result="success",
                docker_required="true",
                docker_verified="false",
                frontend_required="false",
                frontend_verified="false",
                operations_required="false",
                operations_verified="false",
            )
        )
        self.assertEqual(evidence["missing_required"], ["docker_runtime"])
        self.assertEqual(evidence["merge_readiness_ceiling"], "Conditional")


if __name__ == "__main__":
    unittest.main()
