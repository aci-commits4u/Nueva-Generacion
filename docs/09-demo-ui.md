# Demo page (`web/index.html`) and demo script

## Layout (single page, three columns on desktop, stacked on phone)
1. **Traveler panel (left)** — "Your request" textarea prefilled: `Book me NYC to Orlando on Oct 20, nonstop, morning departure, under $300.` Button **Clarify**. Shows questions (if any) and an editable **Requirements card** (chips: Origin JFK/LGA/EWR · Destination MCO · Oct 20 · Depart 6:00–12:00 · Nonstop · ≤ $300.00 · 1 passenger · Refundable: not required). Button **Approve requirements** → shows "Approved 10:42 AM · signed into your Verifiable Intent mandate."
2. **Agent offers (middle)** — two cards from fixtures: **A** SkyWays nonstop JFK→MCO 7:15 AM $260 · **B** SkyWays JFK→PHL→ATL→CLT→MCO 6:05 AM $280 (3 connections). Each card shows "Merchant-signed offer ✓" (after verification). Button **Agent selects this** on each.
3. **Intent Judge result (right)** —
   - Badges: `Mastercard VI chain: valid` · `Merchant signature: valid` · Result `PASS` (green) / `HOLD` (amber) / `BLOCK` (red).
   - Per-check table: check · you approved · merchant offer · status.
   - Traveler message (from LLM; label "explanation, AI-generated").
   - On HOLD: buttons **Choose another flight** and **Accept this exception** (opens a confirm modal quoting the exact change: "I accept 3 connections on offer B (hash …a1f3)").
   - **Buy** button: calls `/api/purchase`; show the 409 message if blocked ("Purchase blocked by Intent Judge: 1 unresolved check (STOPS)").
   - After purchase: **Dispute this** → **Intent Receipt** modal (the evidence packet; one page; print-friendly).
- Footer: "Synthetic demo data. 'Intent-checked' means your approved requirements matched the merchant-signed offer. Not a Mastercard certification."
- Optional dev toggle: "Show raw credentials" (collapsible, truncated JWTs; never keys).

## Visual cues
Plain, high-contrast, large type (projector). Green/amber/red with icons + text (never color alone). Mastercard-neutral styling (do not use Mastercard logos/brand marks).

## 2-minute demo script (Jossue drives, Victor narrates)
1. **Set the scene (10s):** "Alex asks an AI agent to book NYC to Orlando: nonstop, morning, under $300."
2. **Clarify (20s):** type a vague variant first ("NYC to Florida cheap Oct 20") → 2 questions appear ("Which Florida airports?", "Is nonstop required?"). Answer; requirements card fills. **Approve.** "These approved requirements are signed into Mastercard's Verifiable Intent mandate. The agent can't quietly drop 'nonstop.'"
3. **Offer A (15s):** agent selects nonstop $260 → all checks pass → **PASS**. "Most travelers never see us."
4. **Offer B — the client's example (30s):** agent selects $280 with 3 connections → Mastercard chain ✓, merchant signature ✓, **STOPS ✗ → HOLD**. Message: "You asked for nonstop. This itinerary has 3 connections." Click **Buy** anyway → **409 blocked**. "Code enforces this, not the AI."
5. **Exception & dispute (30s):** Accept exception (modal quotes exact change) → Buy succeeds → **Dispute this** → **Intent Receipt**: approved requirements, merchant offer, rule results, *recorded exception* → recommended: traveler (informed consent), final decision: analyst. Then show the alternate: dispute on a PASS purchase where traveler never asked nonstop → recommended: traveler, dispute likely invalid.
6. **Close (15s):** flash test results table (12/12). "The AI never approves anything. It helps the traveler say what they mean, and code holds the agent to it."

## Backup
Record a 90-second screen video as soon as the flow works once. Keep screenshots of each step in `demo-backup/`. Have `MOCK_LLM=1` ready if network fails (say so if asked: "explanations are templated in offline mode").
