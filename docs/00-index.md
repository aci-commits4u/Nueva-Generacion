# Documentation index

Read the problem first, then the workflow and architecture. Documents 01–10 preserve the research and original design. [Implementation status](implementation-status.md) and [the running product](11-running-product.md) describe what is deployed and tested today.

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

These labels distinguish product aspiration from evidence. Detailed proposal examples remain design references; actual file layout, endpoints, supported fields, deployment and verification appear in the implementation documents.

## Implemented product

[Implementation status](implementation-status.md) records the actual supported scope, tests, live model evaluation, deployment, and limits. [DESIGN.md](../DESIGN.md) records autonomous choices. The [execution plan](superpowers/plans/2026-10-13-intent-judge.md) describes the build sequence.

[Running product and operations](11-running-product.md) explains the deployed contracts and budget controls. [Demo script](12-demo-script.md) gives the judge-facing walkthrough. [Final review](final-review.md) records findings, corrections and autonomous rulings.

[Adopting a domain](13-adopting-a-domain.md) explains the actual executable profile format, trusted fact adapters and current registration boundaries.

[Evaluated conversation and continuous quality](15-ai-evaluation-and-conversation.md) documents the conversational revision, actual pipeline comparisons, holdout results, CI and bounded live monitoring.

[Conversational final review](final-review-conversation.md) and [revision ledger](conversation-build-ledger.md) record the independent findings, test-driven fixes, choices and hosted release verification.
- [16 — Product walkthrough](16-product-walkthrough.md): self-explaining overview, tutorial, demo instructions, and design decisions.
