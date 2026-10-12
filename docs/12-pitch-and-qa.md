# Pitch (5 min) and Q&A (2 min)

## Plan
| Time | Beat | Speaker | Slide headline (conclusion) |
|---|---|---|---|
| 0:00–0:30 | Hook | Ryan | "An AI agent booked a flight nobody wanted — and nobody knows who pays." (quote: "NY to Florida, three layovers… who's fault, who's responsible?") |
| 0:30–1:10 | Problem | Alex | "Merchants pay for agent mistakes, so they hold back." ($128/chargeback; travel highest at $120 avg; only 28% open full catalog to agents) |
| 1:10–1:40 | Insight | Ryan | "Verifiable Intent proves the agent was allowed — not that it did what you meant." (quote the spec: not subject to automated verification; does not assign liability) |
| 1:40–2:10 | Solution | Jossue | "Intent Judge: Say it. Sign it. Check it." — the traveler says it (AI clarifies), signs it (approval into the VI mandate), code checks it against the merchant's order, humans decide disputes. Works for any purchase category; flights are today's demo. |
| 2:10–3:50 | Demo | Jossue + Victor | live flow (see `09-demo-ui.md`) + "12/12 scenarios pass" |
| 3:50–4:30 | Trust & roadmap | Barbara | "Built to be trusted: signed requirements, merchant-signed offers, human decisions." Roadmap: prove → pilot (1 airline + Copilot Checkout) → scale in Agent Pay |
| 4:30–5:00 | Close & ask | Alex | "Mastercard proves the agent was allowed. We prove it did what you meant." Ask: pilot with one issuer + one travel merchant, Copilot Checkout as the channel (proposed, not announced) |

Rules: start immediately; say "three layovers" consistently; no "um, so MasterCard, we know MasterCard"; hand off by name; don't read slides; don't claim the AI "can't make mistakes."

## Q&A (Answer → Evidence → Tradeoff → Next) — owners
| Question | Answer | Owner |
|---|---|---|
| Hasn't Mastercard solved this with Verifiable Intent? | It solved *allowed*; its spec says descriptive intent isn't automatically verified and liability is out of scope. We extend it with a signed custom constraint and a checker. | Ryan |
| What if the AI is wrong? | It can't approve. The traveler approves the requirement list, code decides, missing data holds, analysts decide disputes. | Victor |
| Why not just add rules to VI? | We do — our approved requirements *are* a VI constraint. The missing step was turning "nonstop, morning" into explicit, traveler-approved fields. | Victor |
| Who pays under your design? | Evidence decides; we recommend based on what was approved and any recorded exception; analysts decide. | Barbara |
| Who loses the money if the buyer cancels? | Today, the merchant, even when the agent made the mistake. With Intent Judge a mismatched order is held, so nothing is charged. If it's disputed, the merchant has proof of what the cardholder approved, and responsibility follows the evidence, not the easiest party to charge back. For a small business that is the difference between a bad week and a closed shop. | Alex |
| Do you change who is liable? | No. We produce evidence and a recommendation; the analyst decides. Shifting liability needs Mastercard network rules, so that's a pilot question. | Barbara |
| Why does Mastercard need this? | In agentic commerce software picks the payment rail. Cards win if they are the rail that can prove what the person meant. Intent Judge makes that trust visible and agent-native. | Ryan |
| Why would merchants adopt? | Zero integration, and evidence against "I didn't want that" disputes; 93% want agent providers to carry losses — we show who acted outside approval. | Alex |
| What about Amex's protection? | Amex absorbs losses in a closed network; on an open network Mastercard competes with prevention and evidence. | Alex |
| Is "intent-checked" a guarantee? | No. It means approved requirements matched the merchant-signed offer. Liability protection would need Mastercard network rules — that's a pilot question. | Barbara |
| What's live vs mocked? | Live: VI credential creation/verification, merchant signatures, rules engine, enforcement, Foundry explanations. Simulated: the shopping agent's choice, merchant, payment. | Jossue |
| Where's Microsoft? | Foundry agent (clarify/explain), built with GitHub Copilot; Copilot Checkout is the natural pilot channel (it plans Agent Pay integration). | Jossue |
| What would make you wrong? | If travelers find holds annoying or most disputes are buyer's remorse. Pilot measures false-hold rate and dispute outcomes. | Barbara |

## Positioning (agreed Oct 12): innovative, simple, Microsoft lens
- **Innovation in one sentence:** a card payment carries who, how much and where; an AI shopper's payment is missing a field — *what the person meant*. Intent Judge makes it signed and checkable. Mastercard proves the agent was **allowed**; we prove it did what you **meant**.
- **Tagline:** *Say it. Sign it. Check it.* (clarify → approve into the VI mandate → code compares with the merchant-signed order). The AI never approves; humans decide disputes.
- **The artifact:** the **Intent Receipt** — one page the traveler, merchant and bank can all read: what you approved, what was offered, what we found, who decided. Close the demo on it.
- **Breadth, honestly:** one slide shows the same three steps for flights, hotels, subscriptions, each with its typical "not as described" dispute. Say: flights are built; the others are the roadmap (same engine, new category).
- **Microsoft lens:** Microsoft is where agents are born (Copilot, Copilot Checkout, Edge, Windows) and a trusted-AI platform (Foundry); Mastercard is the network and the VI standard. Intent Judge is the handshake between them: Copilot checks intent, then Agent Pay moves the money. Mastercard gets fewer "not as described" disputes, an evidence layer, and merchants opening catalogs to agents (only 28% do today); Microsoft gets trusted agent commerce.
- **Ask:** pilot with one issuer + one travel merchant, Copilot Checkout as the channel *(proposed, not announced)*; measure dispute rate and false-hold rate.
- **Tech mentions:** one line only (Foundry for clarify/explain; Entra + Key Vault are why it is trustworthy in production). No tech-stack slide.

## Money and relevance (agreed Oct 12)
**Headline for the problem-to-solution turn:** *Make the card the safest way for an AI agent to pay.*

**Merchant money, in one breath:** "When an agent buys the wrong thing, the merchant eats the dispute: about $128 a chargeback, plus the goods. A small business can't. We hold the wrong order before anything is charged, and if it's disputed, the merchant has the proof." (Persona is illustrative. Say so.)

**Why this keeps Mastercard relevant (hypotheses, say "we believe"):**
1. *Trust is the moat.* Other rails don't give you dispute rights and evidence. Intent Judge makes that edge agent-native: the payment rail that can prove what you meant.
2. *Distribution.* It reaches agents where they're born: Copilot and Copilot Checkout (proposed pilot channel, not announced).
3. *Standard ownership.* Register category constraints in the open Verifiable Intent spec so agents adopt Mastercard's format.
4. *A network service.* Intent assurance for issuers and merchants, as a pilot question.

**Slide wording rule:** Mastercard is not scoring backend detail. No API, JWT, endpoint or "409" on slides. Say "the payment never leaves the card." Technical answers stay in the Q&A pocket.

## Adoption playbook slide: what each role does
| Agent developer (e.g. Copilot Checkout) | Product manager | Merchant |
|---|---|---|
| 1. Ask the person to approve a short requirement list before shopping | 1. Pick the few requirements that matter per category (flights: stops, departure time, refundable) | 1. Keep signing the order (Verifiable Intent already requires it) |
| 2. Send the merchant-signed order to the check before paying | 2. Design the held moment: what the person sees and when an exception is allowed | 2. Publish the details people care about (refundable, stops) so more orders pass |
| 3. Pay on PASS; show the held screen on HOLD | 3. Track two numbers in the pilot: dispute rate on checked vs unchecked orders, and false-hold rate | 3. Use the Intent Receipt when a dispute arrives |

Footer line for Mastercard: register category constraints in the Verifiable Intent spec; offer intent assurance to issuers.
