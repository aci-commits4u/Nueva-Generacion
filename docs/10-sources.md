# Sources and provenance

Research checked October 13, 2026. Technical conclusions use primary specification, implementation, tests, and provider documentation. The external repositories are not vendored into this branch.

## User inputs

- Victor's pitch ramble and clarification in this conversation: reusable AI intake, task specialization, explicit confirmation, exact-offer exceptions, merchant adoption, and separate demo commerce.
- Victor's pasted "Mastercard Verifiable Intent vs. Our Project" research summary. Treated as a starting hypothesis and checked against the current reference implementation.
- Seven-page pitch deck, reviewed through text extraction and rendered pages: `/Users/victor/Downloads/Team - Nueva Generación.pdf`. The deck is not copied into the repository; its local path is provenance, not a portable repository link.
- Standing project instructions supplied in this conversation: approved requirements, merchant-signed checkout data, deterministic rules, backend refusal, specific exceptions, synthetic data, and the human dispute-decision boundary.

Earlier branch documents were read for context without restoring the previous application into this branch. Their historical claims of working features are not proof that features exist here.

## Verifiable Intent snapshot

Repository: [agent-intent/verifiable-intent](https://github.com/agent-intent/verifiable-intent).

Inspected commit: [`356c29635f1c44df7de02edb58699ca9f29bece6`](https://github.com/agent-intent/verifiable-intent/tree/356c29635f1c44df7de02edb58699ca9f29bece6).

| Primary source | What was checked |
|---|---|
| [README](https://github.com/agent-intent/verifiable-intent/blob/356c29635f1c44df7de02edb58699ca9f29bece6/README.md) | Scope, modes, structured constraints and architecture |
| [Package metadata](https://github.com/agent-intent/verifiable-intent/blob/356c29635f1c44df7de02edb58699ca9f29bece6/pyproject.toml) | Version, Python requirement, license and dependencies |
| [Public exports](https://github.com/agent-intent/verifiable-intent/blob/356c29635f1c44df7de02edb58699ca9f29bece6/src/verifiable_intent/__init__.py) | Issuance and verification APIs available to an adapter |
| [Constraint specification](https://github.com/agent-intent/verifiable-intent/blob/356c29635f1c44df7de02edb58699ca9f29bece6/spec/constraints.md) | Eight registered types, autonomous semantics, extension and unknown-type policy |
| [Credential format](https://github.com/agent-intent/verifiable-intent/blob/356c29635f1c44df7de02edb58699ca9f29bece6/spec/credential-format.md) | Signed checkout guidance, hashes, mandate fields and modes |
| [Security model](https://github.com/agent-intent/verifiable-intent/blob/356c29635f1c44df7de02edb58699ca9f29bece6/spec/security-model.md) | Trust, replay/state, and evidentiary rather than adjudicative scope |
| [Constraint checker](https://github.com/agent-intent/verifiable-intent/blob/356c29635f1c44df7de02edb58699ca9f29bece6/src/verifiable_intent/verification/constraint_checker.py) | Built-in dispatch, unknown-type handling, delegated budget/recurrence handling |
| [Chain verifier](https://github.com/agent-intent/verifiable-intent/blob/356c29635f1c44df7de02edb58699ca9f29bece6/src/verifiable_intent/verification/chain.py) | Signature/binding scope, trust inputs and performed/skipped results |
| [Integrity functions](https://github.com/agent-intent/verifiable-intent/blob/356c29635f1c44df7de02edb58699ca9f29bece6/src/verifiable_intent/verification/integrity.py) | Checkout/payment and reference hash binding |
| [Constraint models](https://github.com/agent-intent/verifiable-intent/blob/356c29635f1c44df7de02edb58699ca9f29bece6/src/verifiable_intent/models/constraints.py) | Preservation of application-defined fields |
| [Autonomous example](https://github.com/agent-intent/verifiable-intent/blob/356c29635f1c44df7de02edb58699ca9f29bece6/examples/autonomous_flow.py) | Real local issuance and separate verification/checking flow |
| [Unknown-type tests](https://github.com/agent-intent/verifiable-intent/blob/356c29635f1c44df7de02edb58699ca9f29bece6/tests/test_constraint_checking.py) | Open-mandate unknown rejection and permissive closed behavior |
| [New-constraint tests](https://github.com/agent-intent/verifiable-intent/blob/356c29635f1c44df7de02edb58699ca9f29bece6/tests/test_new_constraints.py) | Budget/recurrence model recognition |
| [Autonomous tests](https://github.com/agent-intent/verifiable-intent/blob/356c29635f1c44df7de02edb58699ca9f29bece6/tests/test_autonomous_flow.py) | Fixture signing and full-chain verification |

[Executed SDK observations and reproduction](research/vi-sdk-probes.md) list the exact selected tests and direct probes.

## Mastercard context and market data

- [March 5, 2026 Verifiable Intent article](https://www.mastercard.com/us/en/news-and-trends/stories/2026/verifiable-intent.html): official product framing and open-source announcement. Its future-tense integration statements describe publication-time plans, not proof of current commercial availability.
- [Chargeback cost article, updated June 8, 2026](https://www.mastercard.com/mt/en/news-and-trends/Insights/2025/what-s-the-true-cost-of-a-chargeback-in-2025.html): 286 million projected global 2026 chargebacks and $128 merchant cost summary.
- [PYMNTS research summary, September 15, 2026](https://www.pymnts.com/news/artificial-intelligence/2026/ai-makes-the-holiday-shopping-list-but-who-gets-the-sale/): 93% merchant expectation about wrong-choice losses and latest survey sample sizes.

## Related protocols and model provider

- [AP2 specification, v0.2](https://ap2-protocol.org/ap2/specification/): shopping/merchant/credential/processor/trusted-surface roles, autonomous/direct modes, deterministic verification and commerce-protocol boundary.
- [AP2 agent authorization framework](https://ap2-protocol.org/ap2/agent_authorization/): related authorization model; alignment is not proof of a working AP2 integration in Intent Judge.
- [Microsoft structured-output documentation](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs): schema-constrained output, JSON-mode distinction, and provider-specific schema limits.

## Evidence policy

Use exact snapshot links for SDK facts. Re-check those facts before updating the SDK dependency. Avoid inferring commercial network behavior, certification, liability protection, or production performance from local examples or marketing announcements.

The architecture, profile DSL, consent state machine, API contract, and delivery outline are project recommendations synthesized from Victor's requirements and observed integration constraints. They are not upstream VI requirements unless explicitly identified as such.
