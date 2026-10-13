# Security, responsible AI, and evidence

Status: required design safeguards and proposed implementation details. The prototype uses synthetic data only.

## Trust boundaries

| Boundary | Required control |
|---|---|
| Conversation to model | Treat text as data; schema and semantic validation; no tools that can authorize or purchase |
| Model to draft | Reject unknown fields/operators, unsupported normalization, fabricated source spans, and claimed consent |
| Draft to approval | Deterministic review, explicit authenticated action, exact server-stored version |
| Approval to VI | User-role signing binds reviewed requirements and profile version; real deployment needs actual credential/wallet trust |
| Offer to normalized facts | Trusted merchant key, allowed algorithm, identity/time checks, validated signed schema and mapping |
| Constraints to evaluators | Closed registry, instance-level coverage ledger, no silent skips or unsupported enforcement |
| Decision to commerce | Backend gate, exact checkout binding, revalidation, atomic idempotency and execution record |
| Evidence to analyst | Access control, minimal disclosure, immutable references, factual summary, human final decision |

## Prompt injection

Merchant text, traveler text, and agent explanations may contain instructions. They are never executable configuration or authority. Delimit external text in model inputs, provide narrow system instructions, and validate model outputs against the trusted profile.

The principal defense is capability separation: extraction/explanation cannot call purchase, issue consent, modify a profile, set PASS, or create a signed exception. A hostile string that survives into a narrative still cannot change structured results. Escape externally supplied text in the browser rather than inserting it as HTML.

Do not turn a requirement such as "ignore all checks" into workflow instructions. Capture legitimate purchasing preferences where supported; attempts to alter system authority have no operational effect.

## Provenance and key trust

Use separate synthetic signing roles for issuer, user, agent, and merchant. Generate ephemeral demo keys at startup or load keys from environment-managed storage. Do not commit private keys or credential material. Environment configuration never appears in logs, evidence, or model prompts.

An agent cannot choose the issuer root or merchant verification key. Select trusted keys from an application registry. In a production integration, validate key rotation and identity binding. Never fetch arbitrary key URLs from offer text; this also avoids server-side request forgery.

Signatures attest to the signed assertion and signer. They do not establish that a service was actually delivered as described or that an issuer is trusted without a trust policy. Keep delivery evidence as a separate future contract.

## Freshness, consistency, and replay

Validate credential and offer validity windows, intended audiences, nonces, supported types, and necessary disclosures. Recompute checkout hashes from exact signed bytes. Compare checkout and payment amounts/currencies and validate quantity/trip scope.

At purchase, reject a stale requirement/profile/decision version or changed signed checkout. Reserve the authorized execution atomically under a server-generated idempotency key before invoking commerce. Do not treat an HTTP retry as new authority to buy again.

Persistent budgets, subscriptions, and recurrent purchases need accumulated state and their own atomic enforcement. The first single-purchase demo exposes them as unsupported capabilities.

## Evidence packet

Required contents:

- Conversation revision and validated requirement-source references, with minimal necessary disclosure.
- Original approved requirement set and profile identity, revisions, and digests.
- Approval event and signed authorization reference; simulated identity is labeled.
- Original merchant checkout JWT/hash and relevant verified facts, signer identity, and validity window.
- Chain, merchant-signature, native-constraint, and domain-check results, including delegated or incomplete verification responsibilities.
- Specific exceptions, accepted values or uncertainties, signed bindings, and timestamps.
- The exact simulated or live execution receipt and idempotency reference.
- A factual narrative and `"final_decision": "dispute analyst"`.

Store evidence append-only at the application level; use signed records to make key assertions tamper-evident. A mutable local database or an ordinary hash is not an immutable external audit system. Document the demo store's retention and restart limits.

VI's security model describes evidentiary support, not dispute routing, liability assignment, or chargeback adjudication. [VI security model](https://github.com/agent-intent/verifiable-intent/blob/356c29635f1c44df7de02edb58699ca9f29bece6/spec/security-model.md).

## Responsibility recommendations

An optional recommendation may identify an apparent extraction gap, merchant-data contradiction, integrity problem, or bypassed enforcement. It must cite evidence and express uncertainty. Do not automatically blame the customer because a requirement was omitted or because they accepted a different, narrowly scoped exception.

For the initial demo, prefer factual evidence and analyst questions over automatic customer/merchant fault labels. If a recommendation is added, it remains advisory and ends with the human decision boundary. Do not invent network reason codes or claim that customer confirmation settles a dispute.

## Observability

Log IDs, profile/version, decision and check statuses, verification failure categories, model mode/fallback, and execution outcome. Avoid full credentials, signing material, complete model prompts, and unnecessary conversation text. The demo uses no real names, card numbers, or other PII.

## Offline behavior

`MOCK_LLM=1` bypasses model network calls while preserving the same draft/approval/check contracts. Offer verification, native VI checks, domain rules, and purchase enforcement remain real local code. Fake purchases remain visibly fake; a model mock must not also mock cryptographic verification into success.
