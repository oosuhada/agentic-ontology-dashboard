# Enterprise Identity and Access Runbook

## Supported providers

- local development credentials for demo/test environments
- OIDC adapter contract with discovery, allowlisted callback, state, nonce, PKCE, issuer,
  audience, expiry and signing-key validation
- SCIM User/Group adapter contract with tenant scope, idempotency and explicit deprovisioning

Production OIDC is `not_configured` until issuer, client ID, audience, callback allowlist and a
secret-manager reference are provided. The application does not accept a raw ID token or store a
client secret in the frontend or application database.

## Rotation and recovery

1. Add the new signing key to the IdP JWKS and wait for overlap.
2. Verify discovery and a mock login with the new `kid`.
3. Remove the retired key only after the maximum token lifetime.
4. Rotate SCIM and service credentials by creating a replacement, validating its scope, then
   revoking the previous credential.
5. Revoke all sessions for lost devices or deprovisioned users.

High-impact export, marking change, model activation and Action execution call the step-up hook.
Break-glass access remains blocked until a separate credential, incident reason, short TTL and
immutable audit workflow are configured.
