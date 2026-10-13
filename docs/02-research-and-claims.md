# Research, contradictions, and claims

Research date: October 13, 2026. SDK snapshot: [`356c29635f1c44df7de02edb58699ca9f29bece6`](https://github.com/agent-intent/verifiable-intent/tree/356c29635f1c44df7de02edb58699ca9f29bece6). Research execution results are [recorded separately](research/vi-sdk-probes.md).

## Findings that affect our design

| Finding | Evidence | Project implication |
|---|---|---|
| VI is more than an authorization log | [VI overview](https://github.com/agent-intent/verifiable-intent/blob/356c29635f1c44df7de02edb58699ca9f29bece6/README.md) | Credit VI for structured authorization and verification; focus our contribution on capture and domain enforcement |
| The inspected SDK is package 0.1.0, with a draft specification | [Package metadata](https://github.com/agent-intent/verifiable-intent/blob/356c29635f1c44df7de02edb58699ca9f29bece6/pyproject.toml) | Pin a commit; distinguish reference implementation from commercial Mastercard services |
| Chain verification is separate from constraint checking | [Chain verifier](https://github.com/agent-intent/verifiable-intent/blob/356c29635f1c44df7de02edb58699ca9f29bece6/src/verifiable_intent/verification/chain.py) | A chain-valid boolean cannot authorize checkout; the over-price probe confirms this distinction |
| Unknown constraints in open mandates are rejected by the stock checker, even in permissive mode | [Unknown-type tests](https://github.com/agent-intent/verifiable-intent/blob/356c29635f1c44df7de02edb58699ca9f29bece6/tests/test_constraint_checking.py) | Implement and disclose a composite extension verifier; never mislabel an open mandate to obtain a skip |
| Budget and recurrence types are marked checked locally but delegated to network enforcement | [Constraint checker](https://github.com/agent-intent/verifiable-intent/blob/356c29635f1c44df7de02edb58699ca9f29bece6/src/verifiable_intent/verification/constraint_checker.py) | Reject their use until the adapter supplies required state and enforcement |
| Checkout JWT envelope and verification details are implementation-defined in the VI draft | [Credential format, section 6.3](https://github.com/agent-intent/verifiable-intent/blob/356c29635f1c44df7de02edb58699ca9f29bece6/spec/credential-format.md#63-checkout_jwt--checkout-object-representation) | Our merchant profile must require signature verification, trusted keys, and a validated offer schema |
| AP2 now documents v0.2, including deterministic verification and a non-agentic Trusted Surface | [AP2 specification](https://ap2-protocol.org/ap2/specification/) | Keep LLM drafting separate from deterministic consent rendering/signing; no AP2 compliance claim without integration tests |

VI supplies credentials and verification tools; the inspected package does not supply a flight search service, inventory integration, or live payment execution client. [Public exports](https://github.com/agent-intent/verifiable-intent/blob/356c29635f1c44df7de02edb58699ca9f29bece6/src/verifiable_intent/__init__.py). Commerce requires its own adapter.

## Corrections to earlier assumptions

1. **"VI doesn't have customer intent" is too broad.** It records customer-approved instructions and structured constraints. Our concern is whether capture was complete and whether the configured checks evaluate the right domain facts.
2. **"Our custom constraint can simply be skipped" is unsafe.** Prior branch notes suggested avoiding `is_open_mandate=True`. That obscures autonomous semantics. The new integration design explicitly assigns every constraint to an evaluator and fails on unrecognized types.
3. **"All eight types are enforced by one SDK call" overstates the local implementation.** Some responsibilities need another verifier or persistent state. A type appearing in `checked` is not sufficient evidence of enforcement.
4. **"The customer clicked approve, therefore the original request was captured" does not follow.** Coverage review reduces omission risk; it cannot prove perfect understanding.
5. **"An accepted exception permits any purchase" is too broad.** An exception cannot repair invalid signatures or override unchanged signed native constraints. Native violations require fresh authorization and successful verification.
6. **"Configurable for anything" needs a capability boundary.** New prompts can guide intake. New enforceable domains require typed semantics and trustworthy data mappings. Novel computations may require a small reviewed validator or adapter.
7. **The earlier flight-only scope is superseded by Victor's latest direction.** Flights remain the first demonstrator. The core and profiles should be reusable; demo shopping remains separate.

## Pitch figures

| Figure | Verified interpretation | Allowed use |
|---|---|---|
| 286 million | Estimated global chargeback count in 2026 | Broad market problem; never write "$286 million" or label these AI-caused losses |
| $128 | Average merchant third-party fees and internal costs per chargeback in Mastercard's summary | Cost context, with market/sample qualification if using the underlying study |
| 93% | Share of surveyed merchants expecting AI/agent providers to cover wrong-choice losses | Merchant expectations; not current liability allocation or measured adoption |

The first two come from [Mastercard's cost article, updated June 8, 2026](https://www.mastercard.com/mt/en/news-and-trends/Insights/2025/what-s-the-true-cost-of-a-chargeback-in-2025.html). It does not justify multiplying these figures into an estimate of losses caused by agents.

The 93% figure appears in [PYMNTS' September 15, 2026 research summary](https://www.pymnts.com/news/artificial-intelligence/2026/ai-makes-the-holiday-shopping-list-but-who-gets-the-sale/), whose latest survey includes 2,061 U.S. consumers and 60 U.S. retail merchants. Attribute the survey and retain the merchant sample context in supporting notes.

## Claim register

| Statement | Current status |
|---|---|
| We have a documented architecture for conversational capture and domain checks | True on this branch |
| We inspected and exercised the actual VI SDK | True; see research record |
| Our application implements extraction, verification, and enforcement | Not yet true on this branch |
| VI provides structured authorization and cryptographic evidence | Documented upstream |
| The stock VI checker directly evaluates flight connections | Not supported by its registered vocabulary |
| Our framework supports arbitrary requirements without new code | Not a defensible guarantee |
| Our prototype reduces chargebacks or establishes liability protection | Unproven |
| A signed merchant offer proves the merchant delivered the service as described | False; delivery requires separate evidence |
| Mastercard certified or endorsed Intent Judge | No such claim is authorized |

Use "intent-checked" as our application label. Future capability claims require corresponding implemented acceptance tests.
