# ADR-0002: Framework version pins for the foundation

- Status: accepted
- Date: 2026-11-09

## Context
The specification requires Angular + Tailwind, Python + Django REST Framework, PostgreSQL,
Redis + Celery, DeepEval + OpenTelemetry, Docker Compose (§3), but leaves exact versions open.

## Decision
- Python 3.12, Django ~=5.0 (LTS line), djangorestframework ~=3.15, celery ~=5.4,
  psycopg[binary] ~=3.2, redis ~=5.0, django-cors-headers, drf-spectacular (OpenAPI §8),
  cryptography (Fernet authenticated-style envelope encryption for provider secrets §11).
- Node 20 LTS, Angular 18 (standalone components, strict TS), Tailwind CSS 3.4.
- Postgres 16, Redis 7 in Compose.

## Alternatives considered
- Django 4.2: older support window; rejected.
- Angular signals-first rewrite patterns: deferred until feature milestones; the foundation
  uses standard standalone components so later migrations stay incremental.

## Consequences
Reproducible builds via pinned `requirements/*.txt` and `package.json` lockfiles. Version
bumps require an ADR update.
