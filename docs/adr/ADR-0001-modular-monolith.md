# ADR-0001: Modular monolith with async workers

- Status: accepted
- Date: 2026-11-09
- Source: Specification §4 (mandated)

## Decision
Follow the specification's mandated architecture: a single Django application organised into
modular apps, Celery workers for long-running jobs, PostgreSQL as the relational source of
truth, Redis strictly as broker/cache (never the only store for important results), and a
provider adapter boundary isolating vendor SDKs.

## Consequences
- No microservices, Kubernetes, vector DB, or event streaming until a documented requirement
  justifies a change (§1).
- Deployment is Docker Compose based (§12).
- Tenant isolation and permission checks are centralised in the API layer.
