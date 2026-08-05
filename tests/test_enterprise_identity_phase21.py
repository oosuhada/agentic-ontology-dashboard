from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ontology_dashboard.enterprise_identity import (
    EnterpriseIdentityError,
    GroupMapping,
    InMemorySCIMDirectory,
    OIDCValidator,
    ServiceIdentity,
    authorize_service_identity,
    enterprise_identity_readiness,
    evaluate_step_up,
    mock_id_token,
    preview_group_mapping,
)
from ontology_dashboard.identity import AuthError, IdentityService, LoginRequest


NOW = datetime(2026, 8, 6, 2, 45, tzinfo=timezone.utc)


def validator() -> OIDCValidator:
    return OIDCValidator(
        issuer="https://idp.example.test",
        client_id="ontology-dashboard",
        audience="ontology-api",
        callback_allowlist=("https://dashboard.example.test/api/auth/oidc/callback",),
        keys={"mock-v1": b"first-test-key", "mock-v2": b"rotated-test-key"},
    )


def valid_claims(transaction, **updates):
    claims = {
        "iss": "https://idp.example.test",
        "aud": "ontology-api",
        "sub": "subject-123",
        "exp": int((NOW + timedelta(minutes=5)).timestamp()),
        "iat": int(NOW.timestamp()),
        "nonce": transaction.nonce,
        "email": "user@example.test",
        "email_verified": True,
        "groups": ["plant-managers"],
        "amr": ["pwd", "mfa"],
    }
    claims.update(updates)
    return claims


def test_mock_oidc_validates_state_nonce_pkce_issuer_audience_and_key_rotation() -> None:
    oidc = validator()
    transaction = oidc.begin(
        "https://dashboard.example.test/api/auth/oidc/callback",
        now=NOW,
    )
    token = mock_id_token(valid_claims(transaction), key=b"first-test-key")
    claims = oidc.validate(
        id_token=token,
        transaction=transaction,
        returned_state=transaction.state,
        code_verifier=transaction.code_verifier,
        now=NOW,
    )
    assert claims.email == "user@example.test"

    with pytest.raises(EnterpriseIdentityError, match="state") as state_error:
        oidc.validate(
            id_token=token,
            transaction=transaction,
            returned_state="wrong",
            code_verifier=transaction.code_verifier,
            now=NOW,
        )
    assert state_error.value.code == "state_mismatch"

    invalid_audience = mock_id_token(
        valid_claims(transaction, aud="other-api"),
        key=b"first-test-key",
    )
    with pytest.raises(EnterpriseIdentityError) as audience_error:
        oidc.validate(
            id_token=invalid_audience,
            transaction=transaction,
            returned_state=transaction.state,
            code_verifier=transaction.code_verifier,
            now=NOW,
        )
    assert audience_error.value.code == "audience_invalid"

    oidc.rotate_keys({"mock-v2": b"rotated-test-key"})
    with pytest.raises(EnterpriseIdentityError) as old_key:
        oidc.validate(
            id_token=token,
            transaction=transaction,
            returned_state=transaction.state,
            code_verifier=transaction.code_verifier,
            now=NOW,
        )
    assert old_key.value.code == "unknown_kid"
    rotated = mock_id_token(valid_claims(transaction), key=b"rotated-test-key", kid="mock-v2")
    assert oidc.validate(
        id_token=rotated,
        transaction=transaction,
        returned_state=transaction.state,
        code_verifier=transaction.code_verifier,
        now=NOW,
    ).sub == "subject-123"


@pytest.mark.parametrize(
    ("claim_update", "expected_code"),
    [
        ({"iss": "https://evil.example"}, "issuer_invalid"),
        ({"nonce": "wrong"}, "nonce_mismatch"),
        ({"email_verified": False}, "email_unverified"),
    ],
)
def test_oidc_claim_validation_fails_closed(claim_update, expected_code) -> None:
    oidc = validator()
    transaction = oidc.begin(
        "https://dashboard.example.test/api/auth/oidc/callback",
        now=NOW,
    )
    token = mock_id_token(valid_claims(transaction, **claim_update), key=b"first-test-key")
    with pytest.raises(EnterpriseIdentityError) as error:
        oidc.validate(
            id_token=token,
            transaction=transaction,
            returned_state=transaction.state,
            code_verifier=transaction.code_verifier,
            now=NOW,
        )
    assert error.value.code == expected_code


def test_group_mapping_unknown_group_fails_closed_and_never_grants_default_project() -> None:
    mappings = (
        GroupMapping(
            external_group="plant-managers",
            organization_role="member",
            project_roles={"manufacturing-demo-project": "process_manager"},
            approved=True,
        ),
    )
    accepted = preview_group_mapping(("plant-managers",), mappings)
    assert accepted.allowed is True
    assert accepted.project_roles == {"manufacturing-demo-project": ("process_manager",)}
    denied = preview_group_mapping(("plant-managers", "unknown-admins"), mappings)
    assert denied.allowed is False
    assert denied.unknown_groups == ("unknown-admins",)


def test_scim_adapter_is_tenant_scoped_idempotent_paginated_and_deprovisions() -> None:
    directory = InMemorySCIMDirectory()
    first, changed = directory.upsert(
        organization_id="org-a",
        resource_type="User",
        external_id="employee-1",
        payload={"userName": "employee@example.test", "active": True},
    )
    replay, replay_changed = directory.upsert(
        organization_id="org-a",
        resource_type="User",
        external_id="employee-1",
        payload={"userName": "employee@example.test", "active": True},
    )
    other, _ = directory.upsert(
        organization_id="org-b",
        resource_type="User",
        external_id="employee-1",
        payload={"userName": "other@example.test", "active": True},
    )
    assert changed is True
    assert replay_changed is False
    assert replay.id == first.id
    assert other.id != first.id
    assert directory.list(organization_id="org-a", start_index=1, count=1) == (first,)
    disabled = directory.deprovision(
        organization_id="org-a",
        resource_type="User",
        external_id="employee-1",
    )
    assert disabled.active is False
    assert disabled.version == 2


def test_step_up_and_service_identity_scope_isolation() -> None:
    assert evaluate_step_up("model.activate", amr=("pwd",), acr=None).satisfied is False
    assert evaluate_step_up("model.activate", amr=("pwd", "mfa"), acr=None).satisfied is True
    service = ServiceIdentity(
        id="service-1",
        organization_id="org-a",
        project_scopes=("project-a",),
        permissions=("connector.run",),
        expires_at=NOW + timedelta(hours=1),
    )
    assert authorize_service_identity(service, project_id="project-a", permission="connector.run", now=NOW)
    assert not authorize_service_identity(service, project_id="project-b", permission="connector.run", now=NOW)
    assert service.interactive_session_allowed is False


def test_enterprise_readiness_is_not_configured_without_external_secrets(monkeypatch) -> None:
    for name in (
        "ONTOLOGY_DASHBOARD_OIDC_ISSUER",
        "ONTOLOGY_DASHBOARD_OIDC_CLIENT_ID",
        "ONTOLOGY_DASHBOARD_OIDC_AUDIENCE",
        "ONTOLOGY_DASHBOARD_OIDC_CLIENT_SECRET_REF",
        "ONTOLOGY_DASHBOARD_OIDC_CALLBACK_ALLOWLIST",
    ):
        monkeypatch.delenv(name, raising=False)
    readiness = enterprise_identity_readiness()
    assert readiness.state == "not_configured"
    assert readiness.providers[0].state == "ready"
    assert readiness.providers[1].state == "not_configured"
    assert readiness.service_identity["interactive_cookie"] is False


def test_session_revocation_is_visible_across_identity_service_instances(tmp_path: Path) -> None:
    database = tmp_path / "phase21-session.db"
    first = IdentityService(database, app_env="test", seed_demo=True)
    second = IdentityService(database, app_env="test", seed_demo=False)
    _, token, _, _ = first.login(
        LoginRequest(email="manager@ontology.local", password="Manager!2026")
    )
    assert second.principal_for_token(token).email == "manager@ontology.local"
    first.logout(token)
    with pytest.raises(AuthError) as revoked:
        second.principal_for_token(token)
    assert revoked.value.code == "authentication_required"
