# Decisions log

| # | Decision | Why | Date/source |
|---|---|---|---|
| D1 | Solve **agent trust** (not financial inclusion or developer delivery) | Mastercard's own VI spec documents the gap; real open-source code; strong data; low competition; builder-friendly | Team research, Oct 12 |
| D2 | Build **on top of** Verifiable Intent, not a competing standard | Position as extension; credibility with Mastercard judges | Research |
| D3 | ~~Airline bookings only~~ **Superseded by D14** | Client's example; travel = highest avg chargeback ($120) | Discovery + Mastercard data |
| D4 | Add **Clarify** stage | EY partner asked whether it goes back to the person for more info | EY review |
| D5 | **AI never approves**; deterministic rules engine decides; backend enforces | Expert review: model confidence ≠ correctness | Reviewer feedback |
| D6 | Decide on **traveler-approved requirements** stored as VI custom constraint, not `prompt_summary` | Summary is optional/agent-written; could omit "nonstop" | Reviewer feedback; VI constraints.md §6.1 |
| D7 | Read itinerary only from **merchant-signed checkout_jwt** | Avoid "one AI checking another AI's claims" | Reviewer feedback; VI credential-format §6.3 |
| D8 | Missing data = HOLD | Never assume compliance | Reviewer feedback |
| D9 | Exceptions are specific and bound to offer hash | Informed consent must be precise | Reviewer feedback; Goodwin |
| D10 | Rename "verified intent" → **"intent-checked"**; no certification/liability claims | Precision; Mastercard rules would be needed | Reviewer feedback |
| D11 | Responsibility is a **recommendation**; analyst decides | Regulatory caution | Team; open question to confirm with judges |
| D12 | Tech emphasis: Foundry + backend + Mastercard reference code; Entra/Key Vault as production | Avoid an overloaded tech list | Reviewer feedback |
| D13 | Offline `MOCK_LLM` mode | Demo resilience; staff won't fix tech issues | Event rules |
| D14 | **Category-neutral product, flights as the demo.** Added a `category` field and the neutral VI constraint `urn:intent-judge:requirements`; one working category built; generic engine/packs are the architecture story and roadmap | Team finding (Oct 12): not limited to flights. Judges reward innovative, broadly understandable thinking, not build sophistication | Team; `docs/plans/03` |
| D15 | Pitch framing: tagline **"Say it. Sign it. Check it."**; the evidence packet is presented as the **Intent Receipt**; Microsoft lens = handshake between where agents are born (Copilot/Copilot Checkout) and the network (Agent Pay) | Mass-appealing, non-technical, pitchable to Mastercard by a Microsoft employee | Team, Oct 12 |
| D16 | Answer the merchant cash-flow concern with prevention (held orders are never charged), evidence (Intent Receipt) and fair attribution; never claim to move money or shift liability | Discovery concern: a cancelled/disputed order can sink a small merchant; AGENTS rule 8 | Team, Oct 12 |
| D17 | Pitch Mastercard on relevance ("the card is the rail that can prove what you meant"), keep backend off the slides, add an adoption playbook slide (agent developer / product manager / merchant) | Mastercard prioritises staying relevant, not backend detail | Team, Oct 12 |
| D18 | **Three-seat Intent Receipt, merchant as the hero seat.** The receipt opens with Cardholder, Merchant (highlighted), Issuer cards, then the full receipt. Flywheel and network-service ideas are labelled hypotheses | Discovery quotes: "refunds cause issues for the merchant"; services sold to merchants carry the biggest margins; "something that itself brings forth mass adoption" | Team, Oct 12; `docs/02` |
| D19 | **Re-shop is a real step; consent is per check.** "Find another offer" keeps approved requirements, marks the held offer, charges nothing. Each failing or missing check needs its own recorded exception tied to the exact offer | AGENTS rule 6: exceptions must be specific; one blanket "OK" is not consent | Team, Oct 12; D9 |

Open: whether to show responsibility recommendation at all vs evidence only (D11).
