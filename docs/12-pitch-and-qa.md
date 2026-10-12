# Pitch (5 min) and Q&A (2 min)

## Plan
| Time | Beat | Speaker | Slide headline (conclusion) |
|---|---|---|---|
| 0:00–0:30 | Hook | Ryan | "An AI agent booked a flight nobody wanted — and nobody knows who pays." (quote: "NY to Florida, three layovers… who's fault, who's responsible?") |
| 0:30–1:10 | Problem | Alex | "Merchants pay for agent mistakes, so they hold back." ($128/chargeback; travel highest at $120 avg; only 28% open full catalog to agents) |
| 1:10–1:40 | Insight | Ryan | "Verifiable Intent proves the agent was allowed — not that it did what you meant." (quote the spec: not subject to automated verification; does not assign liability) |
| 1:40–2:10 | Solution | Jossue | "Intent Judge: the traveler approves, code checks, humans decide." (5 stages; AI never approves) |
| 2:10–3:50 | Demo | Jossue + Victor | live flow (see `09-demo-ui.md`) + "12/12 scenarios pass" |
| 3:50–4:30 | Trust & roadmap | Barbara | "Built to be trusted: signed requirements, merchant-signed offers, human decisions." Roadmap: prove → pilot (1 airline + Copilot Checkout) → scale in Agent Pay |
| 4:30–5:00 | Close & ask | Alex | "Mastercard proves the agent was allowed. We prove it did what you meant." Ask: pilot with one issuer + one airline |

Rules: start immediately; say "three layovers" consistently; no "um, so MasterCard, we know MasterCard"; hand off by name; don't read slides; don't claim the AI "can't make mistakes."

## Q&A (Answer → Evidence → Tradeoff → Next) — owners
| Question | Answer | Owner |
|---|---|---|
| Hasn't Mastercard solved this with Verifiable Intent? | It solved *allowed*; its spec says descriptive intent isn't automatically verified and liability is out of scope. We extend it with a signed custom constraint and a checker. | Ryan |
| What if the AI is wrong? | It can't approve. The traveler approves the requirement list, code decides, missing data holds, analysts decide disputes. | Victor |
| Why not just add rules to VI? | We do — our approved requirements *are* a VI constraint. The missing step was turning "nonstop, morning" into explicit, traveler-approved fields. | Victor |
| Who pays under your design? | Evidence decides; we recommend based on what was approved and any recorded exception; analysts decide. | Barbara |
| Why would merchants adopt? | Zero integration, and evidence against "I didn't want that" disputes; 93% want agent providers to carry losses — we show who acted outside approval. | Alex |
| What about Amex's protection? | Amex absorbs losses in a closed network; on an open network Mastercard competes with prevention and evidence. | Alex |
| Is "intent-checked" a guarantee? | No. It means approved requirements matched the merchant-signed offer. Liability protection would need Mastercard network rules — that's a pilot question. | Barbara |
| What's live vs mocked? | Live: VI credential creation/verification, merchant signatures, rules engine, enforcement, Foundry explanations. Simulated: the shopping agent's choice, merchant, payment. | Jossue |
| Where's Microsoft? | Foundry agent (clarify/explain), built with GitHub Copilot; Copilot Checkout is the natural pilot channel (it plans Agent Pay integration). | Jossue |
| What would make you wrong? | If travelers find holds annoying or most disputes are buyer's remorse. Pilot measures false-hold rate and dispute outcomes. | Barbara |
