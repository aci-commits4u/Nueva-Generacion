# Documentation index

Read the problem first, then the workflow and architecture. The architecture and contracts are proposed designs for review; they are not claims of completed implementation.

| Document | Purpose |
|---|---|
| [01: Problem and positioning](01-problem-and-positioning.md) | Customer intent, merchant value, omission example, defensible pitch |
| [02: Research and claims](02-research-and-claims.md) | Verified VI behavior, overlap, contradictions, statistics, claim boundaries |
| [03: Product workflow](03-product-workflow.md) | Clarification and approval states, deterministic decision, exact-offer exceptions |
| [04: Architecture](04-architecture.md) | Components, data contracts, proposed endpoints, deployment boundaries |
| [05: Domain profiles](05-domain-profiles.md) | Configuration format, supported operators, flight and hotel examples, general mode |
| [06: VI integration](06-verifiable-intent-integration.md) | SDK use, credential layers, custom constraints, trust and reauthorization |
| [07: Demo and acceptance](07-demo-and-acceptance.md) | Judge-facing comparison and expected future tests |
| [08: Security and evidence](08-security-and-evidence.md) | Injection, signing trust, freshness, replay, neutral evidence |
| [09: Delivery and decisions](09-delivery-and-decisions.md) | Build order, acceptance gates, chosen defaults, open deployment dependencies |
| [10: Sources](10-sources.md) | Primary references, exact SDK snapshot, input provenance |
| [Research: VI SDK probes](research/vi-sdk-probes.md) | What was actually run and observed, including reproduction instructions |

## Status vocabulary

- **Verified upstream:** directly observed in the cited specification, source, or research run.
- **User requirement:** supplied by Victor in this session, including the standing project instructions.
- **Proposed:** a recommended project design that has not been implemented.
- **Unproven outcome:** a business effect requiring future measurement, such as fewer disputes or greater merchant adoption.

These labels distinguish product aspiration from evidence. When the build starts, update status with actual implementation and test results rather than changing proposed behavior into a claim by implication.

## Implemented product

[Implementation status](implementation-status.md) records the actual supported scope, tests, live model evaluation, deployment, and limits. [DESIGN.md](../DESIGN.md) records autonomous choices. The [execution plan](superpowers/plans/2026-10-13-intent-judge.md) describes the build sequence.
