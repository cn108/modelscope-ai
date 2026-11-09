# ADR-0003: Provider secret encryption and rotation

- Status: accepted
- Date: 2026-11-09
- Source: specification §11 (security and secret handling)

## Context

Project provider configurations need API keys for cloud providers. A key must not be
stored in plaintext, returned by the API, written to traces, or committed to source
control. Operators also need a way to rotate keys without invalidating every stored
credential immediately.

## Decision

Store provider secrets in a dedicated one-to-one `ProviderSecret` row, encrypted with
Fernet (AES-128-CBC + HMAC-SHA256). Keys come only from the `PROVIDER_SECRET_KEYS`
environment variable as a comma-separated list:

- the first key encrypts new secrets;
- every configured key is tried when decrypting;
- the secret is write-only at the API boundary;
- provider connection errors are sanitized before reaching clients;
- provider endpoints are separately restricted to prevent SSRF.

This provides authenticated encryption and a controlled rotation path without putting
key material in PostgreSQL or the repository.

## Rotation runbook

1. Generate a new Fernet key.
2. Prepend it to `PROVIDER_SECRET_KEYS`.
3. Restart the API and worker so new writes use the new key.
4. Re-enter/update each provider's API key so its secret is re-encrypted.
5. Verify each provider connection.
6. Remove the old key only after every secret has been re-encrypted.

There is no automatic bulk re-encryption command. A database restore without the matching
key makes provider secrets undecryptable. Keys must be backed up in a secret manager,
separate from the database backup.

## Consequences

- Compromise of the database alone does not expose provider credentials in plaintext.
- Loss of every configured key makes stored secrets unrecoverable; providers must be
  reconnected with new keys.
- Rotating the Django `SECRET_KEY` is unrelated to provider secret encryption; it
  invalidates JWTs but not provider secrets.
- Fernet key rotation is an operator procedure, not a background job. The current code
  supports multiple keys for decryption but does not re-encrypt old rows automatically.
- The provider secret is not included in audit metadata or traces.

## Alternatives considered

- **Plaintext/JSON field:** rejected; violates the specification and exposes keys in
  database dumps.
- **HashiCorp Vault/external secret manager at runtime:** stronger for large deployments,
  but adds infrastructure not required by the specification and complicates local Compose.
  It remains a valid production upgrade.
- **Fernet with a single key:** rejected; makes rotation a flag-day migration.
