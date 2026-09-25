# 0005: Kindling lives under the LaRocca Consulting organization

**Status:** Accepted (2026-09-25)

## Context
Kindling could start under a neutral foundation-style organization or under its
founder's organization.

## Decision
Kindling stays at `github.com/laroccaconsulting/kindling`, maintained by LaRocca
Consulting.

## Consequences
- Code is licensed Apache-2.0, with copyright held by LaRocca Consulting and contributors.
  Contributions are accepted under a DCO sign-off (no CLA).
- PyPI packages (`kindling-*`) are published from this repo via Trusted Publishing, with
  LaRocca Consulting maintainers as owners.
- The hosted demo runs in a LaRocca Consulting AWS account (ADR 0004).
- The work is public and attributable, so docs, ADRs, release notes and write-ups are
  part of the deliverable, not an afterthought.
- Moving to a neutral organization later remains possible if the community grows. GitHub
  transfers keep redirects, and PyPI ownership can be shared.
