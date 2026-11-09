# ADR-0004: Milestone 9 scope — AI security testing vs hardening

- Status: accepted
- Date: 2026-11-09
- Source: specification §13 (roadmap), §14 (testing/definition of done), §17 (acceptance)

## Context

The specification's roadmap defines **Milestone 9 as Hardening**: performance, security
review, documentation, backups, a deployment profile and a full regression suite. During
delivery, the repository used "Milestone 9" for an additional **AI security testing**
feature (reviewed attack cases, actual model responses, pass/fail/inconclusive results).
That feature is implemented, tested and live-verified.

The naming collision creates a risk: a reader could see "M9 complete" and conclude the
specification's final milestone is complete, when hardening is still outstanding.

## Decision

Record the distinction explicitly:

- **Repository M9 / AI security testing** is a delivered feature increment, documented in
  `docs/milestones/MILESTONE-9.md`.
- **Specification M9 / Hardening** remains a separate acceptance milestone. It is not
  considered complete until the hardening checklist in `docs/HANDOVER.md` is closed.
- Status reports must name which "M9" they mean. Do not use "Milestone 9 complete" without
  qualification.

## Consequences

- The feature work is not undervalued: AI security testing is complete and has live
  evidence.
- Docker/PostgreSQL/Redis acceptance and a manual restore drill now pass (2026-11-09).
  The project still cannot be declared specification-complete until rate limiting,
  automated E2E, quality gates, performance/security review, scheduled backups and a
  production profile are delivered.
- Handover documentation and the implementation plan must keep the two tracks separate.
- Future renumbering should avoid reusing a milestone number for extra scope; use an
  extension label (for example "M9 extension: AI security testing") instead.

## Alternatives considered

- **Treat AI security testing as the specification's M9:** rejected; it would misstate
  completion and skip hardening.
- **Rename the feature retroactively:** rejected; it would break commit history, reports
  and the existing pull request. Explicit documentation is less disruptive.
