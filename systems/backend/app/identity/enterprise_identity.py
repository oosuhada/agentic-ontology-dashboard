"""Enterprise identity contracts with fail-closed local test adapters.

The module never accepts an ID token without signature, issuer, audience,
state, nonce and PKCE validation. Production OIDC remains unavailable until a
provider and a secret reference are configured outside the application DB.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


IdentityState = Literal["ready", "not_configured", "blocked", "error"]


class EnterpriseIdentityError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class OIDCProviderStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["local", "oidc"]
    state: IdentityState
    issuer: str | None = None
    client_id_configured: bool
    audience_configured: bool
    secret_reference_configured: bool
    discovery_url: str | None = None
    callback_allowlist: tuple[str, ...] = ()
    jit_policy: Literal["disabled", "invite_only", "approved_groups"] = "invite_only"
    blockers: tuple[str, ...] = ()


class EnterpriseIdentityReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: IdentityState
    providers: tuple[OIDCProviderStatus, ...]
    canonical_context: str = "organization + project membership + permission"
    group_mapping: str = "unknown groups fail closed; approved mappings only"
    scim: dict[str, Any]
    mfa: dict[str, Any]
    service_identity: dict[str, Any]
    session: dict[str, Any]
    break_glass: dict[str, Any]


class OIDCLoginTransaction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: str
    nonce: str
    code_verifier: str
    code_challenge: str
    redirect_uri: str
    created_at: datetime
    expires_at: datetime


class OIDCClaims(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    iss: str
    aud: str | list[str]
    sub: str
    exp: int
    iat: int
    nonce: str
    email: str
    email_verified: bool = False
    groups: tuple[str, ...] = ()
    acr: str | None = None
    amr: tuple[str, ...] = ()


class GroupMapping(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    external_group: str
    organization_role: str | None = None
    project_roles: dict[str, str] = Field(default_factory=dict)
    approved: bool = False


class MappingPreview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    organization_roles: tuple[str, ...]
    project_roles: dict[str, tuple[str, ...]]
    unknown_groups: tuple[str, ...]
    allowed: bool


class SCIMResource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    organization_id: str
    resource_type: Literal["User", "Group"]
    external_id: str
    active: bool
    version: int
    payload: dict[str, Any]


class ServiceIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    organization_id: str
    project_scopes: tuple[str, ...]
    permissions: tuple[str, ...]
    expires_at: datetime
    revoked: bool = False
    interactive_session_allowed: bool = False


class StepUpDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    required: bool
    satisfied: bool
    operation: str
    reason: str


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _json_part(value: dict[str, Any]) -> str:
    return _b64url_encode(json.dumps(value, separators=(",", ":"), sort_keys=True).encode())


def mock_id_token(claims: dict[str, Any], *, key: bytes, kid: str = "mock-v1") -> str:
    header = _json_part({"alg": "HS256", "kid": kid, "typ": "JWT"})
    payload = _json_part(claims)
    signature = _b64url_encode(hmac.new(key, f"{header}.{payload}".encode(), hashlib.sha256).digest())
    return f"{header}.{payload}.{signature}"


class OIDCValidator:
    def __init__(
        self,
        *,
        issuer: str,
        client_id: str,
        audience: str,
        callback_allowlist: tuple[str, ...],
        keys: dict[str, bytes],
        clock_skew_seconds: int = 60,
    ) -> None:
        self.issuer = issuer.rstrip("/")
        self.client_id = client_id
        self.audience = audience
        self.callback_allowlist = callback_allowlist
        self.keys = dict(keys)
        self.clock_skew_seconds = clock_skew_seconds

    def rotate_keys(self, keys: dict[str, bytes]) -> None:
        if not keys:
            raise EnterpriseIdentityError("jwks_empty", "OIDC key set cannot be empty")
        self.keys = dict(keys)

    def begin(self, redirect_uri: str, *, now: datetime | None = None) -> OIDCLoginTransaction:
        if redirect_uri not in self.callback_allowlist:
            raise EnterpriseIdentityError("callback_not_allowed", "OIDC callback is not allowlisted")
        created = now or datetime.now(timezone.utc)
        verifier = secrets.token_urlsafe(48)
        return OIDCLoginTransaction(
            state=secrets.token_urlsafe(32),
            nonce=secrets.token_urlsafe(32),
            code_verifier=verifier,
            code_challenge=_b64url_encode(hashlib.sha256(verifier.encode()).digest()),
            redirect_uri=redirect_uri,
            created_at=created,
            expires_at=created + timedelta(minutes=10),
        )

    def validate(
        self,
        *,
        id_token: str,
        transaction: OIDCLoginTransaction,
        returned_state: str,
        code_verifier: str,
        now: datetime | None = None,
    ) -> OIDCClaims:
        current = now or datetime.now(timezone.utc)
        if current > transaction.expires_at:
            raise EnterpriseIdentityError("oidc_transaction_expired", "OIDC transaction expired")
        if not hmac.compare_digest(transaction.state, returned_state):
            raise EnterpriseIdentityError("state_mismatch", "OIDC state validation failed")
        challenge = _b64url_encode(hashlib.sha256(code_verifier.encode()).digest())
        if not hmac.compare_digest(transaction.code_challenge, challenge):
            raise EnterpriseIdentityError("pkce_mismatch", "OIDC PKCE validation failed")
        parts = id_token.split(".")
        if len(parts) != 3:
            raise EnterpriseIdentityError("token_malformed", "ID token is malformed")
        header = json.loads(_b64url_decode(parts[0]))
        if header.get("alg") != "HS256":
            raise EnterpriseIdentityError("algorithm_denied", "Mock validator accepts HS256 only")
        key = self.keys.get(str(header.get("kid", "")))
        if key is None:
            raise EnterpriseIdentityError("unknown_kid", "ID token signing key is unknown")
        expected = _b64url_encode(hmac.new(key, f"{parts[0]}.{parts[1]}".encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(expected, parts[2]):
            raise EnterpriseIdentityError("signature_invalid", "ID token signature is invalid")
        claims = OIDCClaims.model_validate(json.loads(_b64url_decode(parts[1])))
        if claims.iss.rstrip("/") != self.issuer:
            raise EnterpriseIdentityError("issuer_invalid", "ID token issuer is invalid")
        audiences = {claims.aud} if isinstance(claims.aud, str) else set(claims.aud)
        if self.audience not in audiences and self.client_id not in audiences:
            raise EnterpriseIdentityError("audience_invalid", "ID token audience is invalid")
        now_timestamp = int(current.timestamp())
        if claims.exp + self.clock_skew_seconds < now_timestamp:
            raise EnterpriseIdentityError("token_expired", "ID token expired")
        if claims.iat - self.clock_skew_seconds > now_timestamp:
            raise EnterpriseIdentityError("issued_at_invalid", "ID token issued-at is in the future")
        if not hmac.compare_digest(claims.nonce, transaction.nonce):
            raise EnterpriseIdentityError("nonce_mismatch", "ID token nonce is invalid")
        if not claims.email_verified:
            raise EnterpriseIdentityError("email_unverified", "Verified email claim is required")
        return claims


def preview_group_mapping(groups: tuple[str, ...], mappings: tuple[GroupMapping, ...]) -> MappingPreview:
    approved = {item.external_group: item for item in mappings if item.approved}
    organization_roles: set[str] = set()
    project_roles: dict[str, set[str]] = {}
    unknown: list[str] = []
    for group in groups:
        mapping = approved.get(group)
        if mapping is None:
            unknown.append(group)
            continue
        if mapping.organization_role:
            organization_roles.add(mapping.organization_role)
        for project_id, role in mapping.project_roles.items():
            project_roles.setdefault(project_id, set()).add(role)
    return MappingPreview(
        organization_roles=tuple(sorted(organization_roles)),
        project_roles={key: tuple(sorted(value)) for key, value in sorted(project_roles.items())},
        unknown_groups=tuple(sorted(unknown)),
        allowed=bool(approved) and not unknown,
    )


@dataclass
class InMemorySCIMDirectory:
    """Deterministic test/emulator for the SCIM adapter contract."""

    resources: dict[tuple[str, str, str], SCIMResource] = field(default_factory=dict)

    def upsert(
        self,
        *,
        organization_id: str,
        resource_type: Literal["User", "Group"],
        external_id: str,
        payload: dict[str, Any],
    ) -> tuple[SCIMResource, bool]:
        key = (organization_id, resource_type, external_id)
        existing = self.resources.get(key)
        active = bool(payload.get("active", True))
        if existing and existing.payload == payload and existing.active == active:
            return existing, False
        resource = SCIMResource(
            id=existing.id if existing else f"scim-{hashlib.sha256('|'.join(key).encode()).hexdigest()[:20]}",
            organization_id=organization_id,
            resource_type=resource_type,
            external_id=external_id,
            active=active,
            version=(existing.version + 1) if existing else 1,
            payload=dict(payload),
        )
        self.resources[key] = resource
        return resource, True

    def deprovision(self, *, organization_id: str, resource_type: Literal["User", "Group"], external_id: str) -> SCIMResource:
        key = (organization_id, resource_type, external_id)
        existing = self.resources.get(key)
        if existing is None:
            raise EnterpriseIdentityError("scim_resource_not_found", "SCIM resource does not exist")
        resource = existing.model_copy(update={"active": False, "version": existing.version + 1})
        self.resources[key] = resource
        return resource

    def list(self, *, organization_id: str, start_index: int = 1, count: int = 100) -> tuple[SCIMResource, ...]:
        values = sorted(
            (item for item in self.resources.values() if item.organization_id == organization_id),
            key=lambda item: (item.resource_type, item.external_id),
        )
        start = max(0, start_index - 1)
        return tuple(values[start : start + max(0, count)])


HIGH_IMPACT_OPERATIONS = {
    "export.audit",
    "marking.change",
    "model.activate",
    "action.high_impact",
    "break_glass.open",
}


def evaluate_step_up(operation: str, *, amr: tuple[str, ...], acr: str | None) -> StepUpDecision:
    required = operation in HIGH_IMPACT_OPERATIONS
    satisfied = not required or "mfa" in amr or (acr or "").lower() in {
        "urn:mace:incommon:iap:silver",
        "phrh",
        "phr",
    }
    return StepUpDecision(
        required=required,
        satisfied=satisfied,
        operation=operation,
        reason=(
            "MFA or phishing-resistant authentication is present"
            if satisfied and required
            else "Step-up authentication is required"
            if required
            else "Operation does not require step-up"
        ),
    )


def authorize_service_identity(identity: ServiceIdentity, *, project_id: str, permission: str, now: datetime | None = None) -> bool:
    current = now or datetime.now(timezone.utc)
    return (
        not identity.revoked
        and current < identity.expires_at
        and project_id in identity.project_scopes
        and permission in identity.permissions
        and not identity.interactive_session_allowed
    )


def enterprise_identity_readiness() -> EnterpriseIdentityReadiness:
    issuer = os.getenv("ONTOLOGY_DASHBOARD_OIDC_ISSUER", "").strip().rstrip("/")
    client_id = os.getenv("ONTOLOGY_DASHBOARD_OIDC_CLIENT_ID", "").strip()
    audience = os.getenv("ONTOLOGY_DASHBOARD_OIDC_AUDIENCE", "").strip()
    secret_ref = os.getenv("ONTOLOGY_DASHBOARD_OIDC_CLIENT_SECRET_REF", "").strip()
    callbacks = tuple(
        item.strip()
        for item in os.getenv("ONTOLOGY_DASHBOARD_OIDC_CALLBACK_ALLOWLIST", "").split(",")
        if item.strip()
    )
    blockers: list[str] = []
    if not issuer:
        blockers.append("OIDC issuer is not configured")
    if not client_id:
        blockers.append("OIDC client ID is not configured")
    if not audience:
        blockers.append("OIDC audience is not configured")
    if not secret_ref:
        blockers.append("OIDC client secret reference is not configured")
    if not callbacks:
        blockers.append("OIDC callback allowlist is empty")
    oidc_state: IdentityState = "ready" if not blockers else "not_configured"
    return EnterpriseIdentityReadiness(
        state=oidc_state,
        providers=(
            OIDCProviderStatus(
                provider="local",
                state="ready",
                client_id_configured=True,
                audience_configured=True,
                secret_reference_configured=True,
                jit_policy="disabled",
            ),
            OIDCProviderStatus(
                provider="oidc",
                state=oidc_state,
                issuer=issuer or None,
                client_id_configured=bool(client_id),
                audience_configured=bool(audience),
                secret_reference_configured=bool(secret_ref),
                discovery_url=f"{issuer}/.well-known/openid-configuration" if issuer else None,
                callback_allowlist=callbacks,
                blockers=tuple(blockers),
            ),
        ),
        scim={
            "state": "not_configured" if oidc_state != "ready" else "ready",
            "resources": ["User", "Group"],
            "operations": ["create", "read", "replace", "patch", "deprovision"],
            "idempotency": "organization + resource type + external ID",
            "credential_storage": "hash + external secret reference only",
        },
        mfa={
            "idp_claims": ["amr", "acr"],
            "step_up_operations": sorted(HIGH_IMPACT_OPERATIONS),
            "local_admin": "hook available; TOTP/WebAuthn enrollment not configured",
        },
        service_identity={
            "interactive_cookie": False,
            "scoped": True,
            "expiration_required": True,
            "rotation_required": True,
        },
        session={
            "absolute_expiry": True,
            "idle_expiry": True,
            "rotation": True,
            "client_binding": True,
            "revoke_all": True,
            "cross_instance": "PostgreSQL canonical session store",
        },
        break_glass={
            "state": "not_configured",
            "requirements": ["separate credential", "incident reason", "short TTL", "immutable audit"],
        },
    )


__all__ = [
    "EnterpriseIdentityError",
    "EnterpriseIdentityReadiness",
    "GroupMapping",
    "InMemorySCIMDirectory",
    "MappingPreview",
    "OIDCClaims",
    "OIDCLoginTransaction",
    "OIDCProviderStatus",
    "OIDCValidator",
    "SCIMResource",
    "ServiceIdentity",
    "StepUpDecision",
    "authorize_service_identity",
    "enterprise_identity_readiness",
    "evaluate_step_up",
    "mock_id_token",
    "preview_group_mapping",
]
