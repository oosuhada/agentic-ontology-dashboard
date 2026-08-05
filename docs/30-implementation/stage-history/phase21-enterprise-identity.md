# Phase 21 — Enterprise Identity and Access Lifecycle

- local demo login remains available outside production
- OIDC validation contract covers callback allowlist, state, nonce, PKCE, signature, issuer,
  audience, expiry, verified email and signing-key rotation
- approved group mappings grant explicit organization/Project roles; unknown groups fail closed
- SCIM emulator proves tenant scope, idempotency, pagination and deprovision semantics
- MFA/step-up policy protects high-impact operations
- service identities are expiring, Project/permission scoped and cannot receive interactive cookies
- V4 Identity & access surface displays real configuration blockers

Customer-specific IdP discovery, credentials and local-admin MFA enrollment remain
`not_configured`; no success state is fabricated.
