# Problem and positioning

## The problem

A customer delegates a purchase in ordinary language. The agent must turn that request into a structured authorization and choose an offer. Important requirements can disappear during extraction, remain ambiguous, or be absent from the data used to check the purchase.

A valid signature proves something about the signed record. It does not prove that an interpretation captured everything the customer meant. Even a customer can overlook a missing requirement while reviewing an incomplete list.

Intent Judge attempts to reduce that gap through clarification, visible requirement coverage, explicit customer approval, and deterministic checks against the actual merchant offer. Perfect interpretation is not a product guarantee.

## Three records, three meanings

| Record | Example | Authority |
|---|---|---|
| Original request | "Book me a nonstop flight to Florida under $300." | Input to extraction and review; useful evidence of a possible omission |
| Approved requirements | Reviewed destination airports, dates, USD ceiling, and zero connections/other intermediate stops | Current source of purchasing intent after explicit customer confirmation |
| Proposed purchase | Merchant-signed $280 itinerary with three connections | Source of purchase facts after signature, identity, freshness, and schema checks |

The original sentence leaves details unresolved: origin, travel date, which Florida airport, and the meaning of the price boundary. The system must clarify these rather than invent them. The nonstop requirement is explicit and must appear in the review.

## Strongest example

An illustrative baseline records permitted products, merchant, and price limit but omits nonstop. Its approved product scope includes both a nonstop and a connecting itinerary. The connecting $280 offer can satisfy the recorded VI constraints if every other applicable check passes.

Intent Judge's comparison flow extracts nonstop, asks about unresolved travel details, and shows the original words alongside the proposed requirements. After the customer confirms zero stops, the same signed connecting offer fails our domain check and checkout is held.

The comparison demonstrates an omission in the illustrative application. It does not demonstrate a defect that every VI-enabled application has: another developer could capture and enforce the same requirement through product restrictions or custom validators. See [the demo contract](07-demo-and-acceptance.md).

## Who benefits and who integrates

The customer's benefit is control over tradeoffs that otherwise become agent assumptions. The merchant's benefit is fewer preventable mismatches and clearer evidence of the customer's approved choices. Both benefits need measurement.

An agent platform or wallet may host the conversational intake and confirmation experience. A merchant, checkout provider, or coordinating platform may enforce the decision before execution. A merchant cannot reconstruct an absent customer approval record from a prompt it never received; the parties must agree on a consent and offer contract.

Adoption therefore means making the layer easy to integrate at both boundaries: accepting a trustworthy approval record and evaluating a trustworthy offer. It does not mean requiring merchants to rebuild their storefront or use our shopping agent.

## What we add

- A reviewable mapping from conversational requirements to structured fields, including unresolved and unsupported requests.
- A reusable approval and exception workflow across task profiles.
- Deterministic domain checks for attributes the built-in VI vocabulary does not directly evaluate.
- Evidence linking the conversation, approved version, offer, check results, and exact exceptions.

VI remains the cryptographic foundation. Its documented constraint vocabulary already covers merchants, payees, products, amounts, budgets, recurrence, and checkout/payment references. [Constraint specification](https://github.com/agent-intent/verifiable-intent/blob/356c29635f1c44df7de02edb58699ca9f29bece6/spec/constraints.md).

## Pitch

> Agentic commerce needs purchases people can trust. Intent Judge clarifies the request, records what the customer approves, checks the merchant's actual offer, and documents any exceptions the customer knowingly accepts. It builds on Mastercard Verifiable Intent with reusable conversational and domain-specific enforcement.

Flights make the problem concrete. Hotels demonstrate that the workflow can be reused. Broader compatibility depends on supported profiles, data contracts, and integration partners.
