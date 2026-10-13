# The self-explaining product experience

Open the [public product](https://intent-judge-perfected.vercel.app). Start with **Show me how**. The five-step walkthrough explains the product using a synthetic flight example without calling Foundry, authorizing rules, or buying anything.

1. **Say what matters.** A nonstop flight to Florida under $300 is a request, not an authorization.
2. **Fill the gaps.** Clarify airports and date instead of letting the agent guess. The live system extracts a draft and separately audits coverage against customer words.
3. **Review the rules.** The traveler checks every field, chooses explicit no preferences, and approves the exact requirements.
4. **Check the offer.** $295 nonstop matches the example; $280 with three connections violates nonstop. The working backend checks merchant-signed facts and holds checkout.
5. **Make a choice and keep the record.** Choose a match or accept each eligible difference for the exact offer. Integrity failures cannot be waived. Download evidence for a dispute analyst.

**Try the working demo** opens live Foundry intake. Choose Flights, Hotels, or General, then write a request or use an example. The conversational assistant asks the next useful question; the intent panel shows the captured requirements and source quotations. Choose **Review requirements**, explicitly review the rules, then approve. Compare the two synthetic offers and their deterministic checks. **Simulate purchase** creates a demo receipt. **Download evidence** exports the signed record. No real booking or payment is created.

**What happens here?** gives plain-language instructions at each demo step. **How it works** replays the tutorial, and **Back to your demo** returns to the current draft. Local review corrections stay intact when opening tutorial or Quality. Root opens the overview with an explicit **Resume your latest demo** link when a saved intent exists; explicit `?intent=...` URLs resume saved drafts/receipts in the same browser session. **Quality** explains measured model evaluations and the daily live canary.

Offline mode stays an explicit emergency choice under Interpretation settings. It is never an automatic replacement for Foundry. The tutorial is a local teaching aid, not a model fallback or a live verification result.

## Design decisions

Swiss typography and conceptual flight diagrams, warm white canvas, forest ink, lime match indicators, amber holds. Locally hosted Geist Sans. Compact navigation replaces the fixed sidebar. The landing page explains the interpretation gap and the separate value to customers and merchants. No unsupported chargeback reduction, Mastercard certification, or liability claims.

Stitch's tools were available but its connector returned Authentication required. Stitch-compatible design guidance was applied in `.stitch/DESIGN.md`; local generated hero and walkthrough references were inspected before implementation. There is no claimed Stitch project/upload.
