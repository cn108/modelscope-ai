# ADR-0005: Provider adapter scope for this release

- Status: accepted, with a known specification gap
- Date: 2026-11-09
- Source: specification §3/§4 (AI integrations), §11 (SSRF/secret handling), §15
  (provider setup guides)

## Context

The specification names four provider families: cloud/OpenAI-compatible APIs, Hugging
Face, LM Studio and Ollama. The implementation currently has two concrete adapters:

- **Z.ai** — a fixed, verified OpenAI-compatible cloud endpoint with an API key;
- **Ollama** — the local Ollama HTTP API, restricted to loopback/host-gateway endpoints on
  port 11434.

The local endpoint validator is intentionally narrow to prevent the application from
being used as an SSRF proxy. That validator rejects LM Studio's usual port 1234 and `/v1`
path, as well as arbitrary LAN/cloud URLs. There is no Hugging Face client or generic
OpenAI-compatible config.

## Decision

Ship this release with **Z.ai and Ollama only**. Do not claim LM Studio, Hugging Face or
generic OpenAI-compatible support in the UI or documentation. Document the gap honestly
and keep the adapter boundary ready for additional providers.

A new provider requires:

1. a `ProviderAdapter` implementation;
2. a new `ProviderConfig.Kind` choice and serializer validation;
3. endpoint/SSRF rules appropriate to that provider;
4. secret handling through the existing encrypted-secret path;
5. adapter, connection, error-redaction and permission tests;
6. a setup/troubleshooting guide.

## Consequences

- Users can evaluate a cloud model (Z.ai) and a local model (Ollama) today.
- LM Studio users cannot use the app through the current validator. Pointing them at an
  Ollama adapter would fail and would give misleading instructions.
- The specification's provider coverage is incomplete; this is tracked in
  [HANDOVER.md](../HANDOVER.md) and must be resolved or explicitly descoped with the
  owner.
- The adapter boundary, model catalogue and encrypted-secret design remain reusable for
  future providers.
- A future generic OpenAI-compatible adapter must still enforce an operator-controlled
  endpoint allow-list; do not simply accept arbitrary URLs.

## Alternatives considered

- **Treat LM Studio as Ollama:** rejected; the port/path contract differs and the current
  validator correctly rejects it.
- **Allow arbitrary base URLs:** rejected; creates SSRF and credential-exfiltration risk.
- **Add all four adapters in this change:** out of scope for a documentation/handover
  pass and would require new provider-specific tests and live verification.
