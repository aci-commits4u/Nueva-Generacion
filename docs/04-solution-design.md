# Solution design — Intent Judge

## One-liner
Mastercard's Verifiable Intent proves an AI agent was **allowed** to buy. Intent Judge makes sure it bought what the person **meant**.

## Division of labor (the key design idea)
| Who | Does | Never does |
|---|---|---|
| **AI (Foundry model)** | Turns the request into structured requirements; asks about missing ones; explains results in plain language; drafts the evidence narrative | Approve, pass, or authorize anything |
| **Code (rules engine + VI verifier)** | Verifies the VI chain and merchant signature; compares approved requirements with the merchant offer field by field; decides PASS / HOLD / BLOCK; enforces at the purchase endpoint | Interpret free text |
| **Humans** | Traveler approves requirements and any specific exception; dispute analyst makes the final call | — |

Pitch line: **"The AI never approves anything. It helps the traveler say what they mean, and code holds the agent to it."**

## The flow (5 stages)
1. **Clarify & extract** — Traveler types: "NYC to Florida, nonstop, under $300, Oct 20 morning." Foundry returns draft `requirements` + up to 2 `questions` for anything missing/ambiguous (e.g., "Which Florida airport(s) are OK?", "Is a refundable fare required?"). Unspecified ≠ requirement.
2. **Approve** — Traveler sees the exact requirement list as checkboxes/fields and confirms. The approved list is stored as `ApprovedRequirements` and embedded in the VI **L2 checkout mandate** as custom constraint `urn:intent-judge:flight-requirements`, signed by the user key. (Also keep standard VI constraints: amount range = max price, allowed merchants.)
3. **Check** — The shopping agent (simulated in our demo) selects an offer. The **merchant** signs a `checkout_jwt` containing the itinerary. Our backend: verifies the VI chain (Mastercard SDK) and the merchant signature → extracts itinerary from the signed payload → `rules_engine.evaluate(approved_requirements, offer)` → PASS / HOLD / BLOCK with per-check results.
4. **Explain & confirm** — Foundry turns the check results into one sentence for the traveler ("You asked for nonstop. This itinerary has 3 connections."). Traveler can **cancel/choose another**, or **accept the specific exception** (recorded with check id, accepted value, offer hash, timestamp). Purchase endpoint enforces.
5. **Evidence (only if disputed)** — One-page packet for the issuer's dispute analyst: VI chain result, approved requirements, merchant-signed offer, rule results, recorded exceptions, suggested reason code, **recommended** responsibility, `final_decision: dispute analyst`.

## Who sees what
- **Traveler:** only sees Intent Judge when clarifying (stage 1–2) or on a HOLD (stage 4). Matching purchases go straight through.
- **Dispute analyst:** sees the evidence packet only if there's a dispute.
- **Merchant:** no UI; the order carries an **"intent-checked"** marker = *"traveler-approved requirements matched the merchant-signed offer at time of purchase."* It is **not** Mastercard certification and grants **no** liability protection today (that would require Mastercard network rules — roadmap).

## Why this beats alternatives
- Dispute-only tool: doesn't prevent loss.
- More rules in VI alone: can't capture natural language ("nonstop, morning") without a step that structures it — that's our Clarify/Approve stage, and we then *do* express it as a VI constraint.
- Absorb losses like Amex: too costly on an open network; we compete with evidence and prevention.

## Scope
**In:** airline bookings; synthetic data; clarify/extract; approve; deterministic check; explain; exceptions; purchase enforcement; evidence packet; 12-case test set; demo page; offline mock mode.
**Out:** live payments; real Mastercard/merchant/cardholder data; live dispute systems (Mastercom/Ethoca); automated liability decisions; non-flight categories (roadmap: hotels, retail, subscriptions); agent registration (Agent Pay covers it); production deployment.

## Roadmap (for the pitch)
1. **Prove it** (today): prototype on synthetic airline bookings.
2. **Pilot** (~3 months, assumption): 1 issuer + 1 airline or OTA, Microsoft **Copilot Checkout** as channel; measure dispute rates on intent-checked vs unchecked agent purchases, and false-hold rate.
3. **Scale** (6–12 months, assumption): service in Agent Pay intent APIs; more categories; propose the flight-requirements constraint for registration in the VI spec (namespace `mandate.checkout.*`).

## Concern → solution traceability (official checklist item)
| Client concern | Where solved |
|---|---|
| "Who's fault, who's responsible?" | Evidence packet with recommended call; analyst decides |
| "Real agent making a real transaction?" | VI chain verification (Mastercard SDK) before anything else |
| "Books layovers when I don't want" | Clarify/Approve + deterministic stops check |
| "Can't force merchants" | Zero merchant integration; intent-checked marker gives them evidence; opt-in |
| "Always money" | Fewer "not as described" disputes ($128 each; travel costliest at $120 avg) |
| "Competitors" | Builds on Mastercard's own open standard; open-network answer to Amex |
| Out of scope (stated openly) | Live payments, live dispute systems, automated legal decisions, non-flight categories |
