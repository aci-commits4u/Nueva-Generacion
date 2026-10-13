# Delivery order and design decisions

Status: original delivery outline. The subsequent application build and separate Vercel release are recorded in [implementation status](implementation-status.md), [the execution plan](superpowers/plans/2026-10-13-intent-judge.md) and [release review](final-review.md).

## Build sequence

1. **Pure deterministic engine and contracts.** Implement structured checks, missing-value semantics, non-waivable gates, approved requirement versions, and exact-offer exceptions. Start with flight fixtures and focused rule tests. Keep all network/LLM work outside `rules_engine.py`.
2. **Real VI and offer verification.** Pin the researched SDK, issue synthetic L1/L2/L3, bind approved flight requirements, verify merchant checkout signatures and hashes, and prove the composite custom-constraint design. Test native amount failures and unknown types.
3. **API and execution enforcement.** Add immutable approval records, HTTP 409 refusal, reauthorization and exception binding, freshness checks, and idempotency. Obtain one SDK-backed end-to-end synthetic scenario before further breadth or polish.
4. **Foundry intake and explanation.** Add the bounded model client, provenance/coverage review, structured output validation, and `MOCK_LLM=1`. Demonstrate that model approval language cannot bypass the backend.
5. **Small demo surface and separate commerce.** Natural-language intake, profile-derived review controls, signed offer comparison, exception confirmation, and evidence packet. The demo commerce adapter supplies synthetic catalog and simulated purchase only.
6. **Scenario suite and profile reuse.** Complete [acceptance scenarios](07-demo-and-acceptance.md), then demonstrate a second hotel profile. The shared core must enforce it, rather than merely render another page.

This preserves the project's priority: correct rules and a real end-to-end flow before UI polish. If the halfway checkpoint lacks an end-to-end scenario, cut visual polish and secondary domains first.

## Decision register

| ID | Decision/default | Basis and status |
|---|---|---|
| D01 | Reusable core plus versioned task profiles | Victor's latest direction; proposed concrete contract |
| D02 | Flights first, hotels as evidence of reuse | Existing synthetic demo context; proposed sequence |
| D03 | General mode preserves unsupported requirements and holds execution | Requirement for broad intake without false universal enforcement |
| D04 | AI drafts/clarifies/explains; deterministic code decides | Standing non-negotiable project rule |
| D05 | Customer-approved object is authoritative; conversation supplies coverage and evidence | Standing rule and omission failure example |
| D06 | Approved flight object stays in `urn:intent-judge:flight-requirements` | Standing integration requirement |
| D07 | Native checks plus explicit custom evaluator composition | Verified stock SDK unknown-type behavior; proposed adapter extension |
| D08 | Verified signed checkout is source of purchase facts | Standing security rule; stronger application contract than draft envelope guidance |
| D09 | Exceptions preserve original findings and require exact-offer signed authority | Victor's workflow; proposed signed implementation |
| D10 | Native VI violations require valid fresh authorization | Prevents an application exception from bypassing signed native limits |
| D11 | Demo discovery/execution is separately injected | Victor's explicit separation requirement |
| D12 | Single purchase only until stateful recurrence/budget enforcement exists | Verified limits of the local SDK checker |
| D13 | Neutral evidence first; any responsibility recommendation remains advisory | Standing analyst-final-decision boundary |
| D14 | No new frontend framework/build step | Standing stack and short demo scope |
| D15 | Local deterministic offline path | Standing `MOCK_LLM=1` requirement |
| D16 | Pin external SDK snapshot; reverify changes | Evolving upstream draft and research reproducibility |

## Implementation questions to resolve before the affected integration

- **Deployment owner:** which party hosts intake, trusted approval, and purchase enforcement? The demo can simulate roles together; production consent needs an agreed trust model.
- **Foundry access:** actual project, deployment, endpoint style, structured-output support, and quota. These are not assumed configured or copied from other tools.
- **Wallet/customer signing:** synthetic approval keys for the demo; real user authentication and key custody require a partner integration.
- **Merchant schema and keys:** synthetic fixture registry initially; live signed itinerary/room data and trusted key distribution need a real contract.
- **Storage:** single-process ephemeral evidence versus persistence across restart. Choose deliberately before claiming retained evidence.
- **Round-trip scope:** the flight profile documents both legs, but the first scenario can be one-way. Round-trip support cannot be claimed until its checks and signed all-in totals work.
- **Custom-validator interoperability:** prove our composite adapter locally; identify whether a target partner recognizes the application constraint types.

These dependencies do not prevent documentation or the offline synthetic demonstrator. They bound claims about production readiness.

## Success measures after implementation

Technical measures: refusal-path correctness, omission detection on a labeled evaluation set, false-pass and false-hold rates, supported-profile coverage, exact-offer execution binding, and no model authority leakage.

Product measures: completion time and friction for clarification/confirmation, correction rate in the review screen, integrator effort to add a second domain, and customer comprehension of exceptions.

Business hypotheses: fewer avoidable mismatches, less ambiguity during dispute review, and greater merchant willingness to accept agent purchases. Validate through future pilots; no current metric establishes those outcomes.

## Documentation maintenance

When implementation starts, add an explicit implemented-capability table with links to tests. Update this register when changing semantics. Preserve the distinction between source facts, design decisions, synthetic observations, and production evidence.
