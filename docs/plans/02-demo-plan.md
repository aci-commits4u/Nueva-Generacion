# Plan 2 — Final demo: what the judges see

> **Status: DRAFT — pending confirmation by Jossue + Victor.** Builds on `docs/09-demo-ui.md` and `docs/12-pitch-and-qa.md`; this plan changes the *timing* and adds the *determinism* the original lacks.
> Decision IDs (D-x) refer to `docs/plans/01-build-plan.md` §0.

## 1. The one-sentence demo

Alex asks an AI agent to book NYC→Orlando. We show the agent buying a clean flight without friction, then trying a **three-layover** flight the traveler never wanted — and **code**, not AI, refuses the purchase until the traveler records a specific exception. Then we show the evidence a dispute analyst would get.

Pitch line to land: **"The AI never approves anything. It helps the traveler say what they mean, and code holds the agent to it."**

## 2. Timing fix (the original script doesn't fit)

`docs/12` gives the demo **1:40** (2:10–3:50). `docs/09` scripts **2:00**. Proposed 98-second cut (total 1:38, under the 1:40 cap):

| Clock | Secs | What happens on screen | Say (Victor narrates, Jossue drives) | What it proves |
|---|---|---|---|---|
| 0:00–0:15 | 15 | Page loads with vague request prefilled: *"NYC to Florida cheap, Oct 20"* → **Clarify** → 2 questions with one-click chips (*MCO* · *nonstop required*) → requirement card fills → **Approve** | "Alex asks an AI agent to book a flight. The AI asks what's missing. Alex approves the exact list, and it's signed into Mastercard's mandate, so the agent can't quietly drop *nonstop*." | Clarify stage (EY's question); AI = understand only |
| 0:15–0:23 | 8 | Agent selects **Offer A** (nonstop, $260) → checks pass → **PASS**, order goes through with zero extra taps | "A matching order goes through with zero extra taps, like tap-to-pay. Most travelers never see us." | Seamless on matches; adoption needs no new habit |
| 0:23–0:40 | 17 | Agent selects **Offer B** (JFK→PHL→ATL→CLT→MCO, $280) → signature checks ✓, **STOPS ✗ → HOLD** → *"You asked for nonstop. This itinerary has 3 connections."* → **Buy** is refused | "Signed, under budget, and not what Alex meant. The AI worded that sentence; it didn't make the call. Nothing was charged. The payment never leaves the card, so the merchant never carries an order nobody wanted." | The client's exact example; enforcement; merchant protected |
| 0:40–0:46 | 6 | Click **Find another offer** → offer B is marked **Held** with its failed check (STOPS); approved requirements stay; funds strip still says *Nothing was charged*; the agent keeps looking | "Alex can send the agent back out. The requirements stay, B is marked held, and nothing is charged." | Re-shop is a real step, not a reset |
| 0:46–1:00 | 14 | Open the Held offer B → per-check box reads *"I accept 3 connections (Connections) on this exact offer"* → tick it → **Buy** now succeeds | "Alex decides this one is worth it. Each exception is one specific check, tied to this exact offer." | Exceptions are specific (AGENTS rule 6) |
| 1:00–1:08 | 8 | **Dispute this** → Intent Receipt opens | "Later, Alex disputes it. The analyst gets one page." | Evidence exists before the argument |
| 1:08–1:24 | 16 | **Three seat cards** side by side: Cardholder · **Merchant (highlighted, the hero card)** · Issuer, each with a headline and three lines; scroll cue to *Full receipt* below. Caption: *"One transaction, three seats, one shared record."* | "One transaction, three seats. The merchant sees proof of what the cardholder approved instead of just a loss. The cardholder sees what was agreed. The issuer sees the evidence, and the analyst decides." | Merchant is the commercial heart; recommendation only, analyst decides |
| 1:24–1:30 | 6 | Flash the results table: **12/12 scenarios pass** | "Twelve scenarios, including tampering and prompt injection." | Tested, not staged |
| 1:30–1:38 | 8 | Back to the highlighted merchant card | **Closing line:** "We believe checked orders mean fewer disputes, so merchants want the badge, so agents prefer the checked rail, so more cardholders trust agents." | Adoption flywheel (hypothesis, a pilot question) |

Total: 15 + 8 + 17 + 6 + 14 + 8 + 16 + 6 + 8 = **98 s (1:38)**.

**Find another offer beat:** it is its own 6-second beat (0:40–0:46). It does not replace another beat. The exception beat was shortened to make room, and the "Accept exception" modal is replaced by the per-check checkbox.

**Moved to the Q&A pocket (ready, not scripted):** dispute on a PASS purchase ("I wanted nonstop" when never approved → `traveler`); **Tamper toggle** → BLOCK + `fraud_path`/4837; scenario 9 (summary omitted *nonstop*) and 10 (agent misdescribes offer).

## 3. What the page looks like (final state, after the HOLD)

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│ Intent Judge                                         synthetic demo data   [Reset demo]  │
├───────────────────────┬─────────────────────────────┬────────────────────────────────────┤
│ 1 YOUR REQUEST        │ 2 AGENT'S OFFERS            │ 3 INTENT JUDGE                     │
│ ┌───────────────────┐ │ ┌─────────────────────────┐ │  VI chain: valid ✓                 │
│ │NYC to Florida...  │ │ │ A  SkyWays  nonstop     │ │  Merchant signature: valid ✓       │
│ └───────────────────┘ │ │ JFK→MCO 7:15 AM  $260   │ │  ┌──────────────────────────────┐  │
│ [Clarify]             │ │ Merchant-signed ✓       │ │  │  ⚠ HOLD  — 1 unresolved check │  │
│                       │ │ [Agent selects this]    │ │  └──────────────────────────────┘  │
│ Requirements ✓ appr.  │ └─────────────────────────┘ │  Check    You approved  Offer  St. │
│ From JFK·LGA·EWR      │ ┌─────────────────────────┐ │  STOPS    Nonstop       3 conn ✗   │
│ To   MCO              │ │ B  SkyWays  3 connections│ │  PRICE    ≤ $300        $280   ✓   │
│ Oct 20 · 6AM–12PM     │ │ JFK→PHL→ATL→CLT→MCO     │ │  DATE     Oct 20        Oct 20 ✓   │
│ Nonstop · ≤ $300      │ │ 6:05 AM  $280           │ │  …                                  │
│ 1 passenger           │ │ Merchant-signed ✓       │ │  "You asked for nonstop. This       │
│ Approved 11:52 AM     │ │ [Agent selects this]    │ │   itinerary has 3 connections."     │
│                       │ └─────────────────────────┘ │   (AI-generated explanation)        │
│                       │                             │  [Choose another] [Accept exception]│
│                       │                             │  [Buy]  → 409 Purchase blocked ...  │
├───────────────────────┴─────────────────────────────┴────────────────────────────────────┤
│ "Intent-checked" = your approved requirements matched the merchant-signed offer.          │
│ Not a Mastercard certification.                                                           │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

**Added since this wireframe:**
- **Held-offer badge.** After **Find another offer**, the offer card for B shows a **Held** badge with its failed check (STOPS: 3 connections). Approved requirements stay in column 1. Nothing is charged.
- **Per-check consent.** In column 3, each failing or missing check gets its own checkbox sentence (for example *"I accept 3 connections (Connections) on this exact offer"*). **Buy** stays refused until every failing or missing check has one.
- **Three-seat Intent Receipt.** The receipt opens with three cards side by side: Cardholder, **Merchant (hero card, highlighted)**, Issuer. Each has a headline and three lines. The detailed receipt sits below under **Full receipt**. Caption: *"One transaction, three seats, one shared record."*

Design rules for a projector: large type, high contrast, status always **icon + text + color** (never color alone), no Mastercard logos or brand marks, mobile stacks columns. AI text is always labelled "AI-generated explanation". A small badge appears only when running on fallback: `offline mode — templated explanation`.

## 4. Things the original script lacks — added so the demo is repeatable

| Addition | Why |
|---|---|
| **`POST /api/reset` + [Reset demo] button** | Rehearse back-to-back; recover from any mistake in one click |
| **One-click answer chips** for the 2 clarify questions | Typing on stage is the slowest, riskiest step |
| **Scenario presets** (`?scenario=tamper`) behind a hidden dev toggle | Q&A pocket demos in 10 s without live-editing JWTs |
| **Click-only flow** (no keyboard after load) | Fewer failure modes while narrating |
| **Never quote an offer reference aloud** | Each check signs a fresh merchant order (timestamp + randomized signature), so the short reference on screen differs every run. Say "this exact offer" and point at the screen |
| **Funds strip + "What this means for the merchant"** | Answers "who loses the money?" on screen with no extra talk track: a HOLD shows *Nothing was charged*; the receipt states what the evidence means for the merchant |
| **LLM timeout 3 s → mock** (D-C) | A slow model can't stall the room; the badge keeps us honest |

## 5. Live vs simulated (say it first if asked)

| Live | Simulated |
|---|---|
| VI credential creation + verification, merchant signature check | The shopping agent's choice of offer |
| Rules engine, 409 enforcement, exception binding to `offer_hash` | The airline/merchant and payment |
| Foundry extract + explain (or labelled offline mode) | The dispute system; all identities and keys (labelled demo keys) |

If the VI fallback ladder (Plan 1 §6) drops to rung 3, this table changes and the Q&A answer must too.

## 6. Backup plan

1. **Recorded video, 90 s,** captured the first time the full flow works, then re-recorded after freeze. File: `demo-backup/demo.mp4` (+ copy on a phone).
2. **Screenshots of each step** in `demo-backup/` for slides.
3. **`MOCK_LLM=1` ready** — one env var, tested; say "explanations are templated in offline mode" if asked.
4. **Localhost only** (D-B). Laptop on power, notifications off, browser zoomed to ~125%, one tab, page pre-loaded and reset.
5. **Failure responses:** model fails → badge appears, keep going. Server dies → play video, narrate over it. Never debug live.

## 7. Rehearsal standard

Two timed full runs with the whole pitch before submitting: demo ≤ 100 s, no clicking the wrong card, narration hands off by name. Anything that failed once gets a fix or a cut — not a hope.

## 8. How the demo maps to what judges reward

| Judge lens (from the kit) | Where it shows |
|---|---|
| Hook → Problem → Discovery → Solution → **Demo** → Impact | Demo is Offer B = the client's own "three layovers" example |
| Real functionality, honest about mocks | §5 table |
| AI behaviour + limits | AI only clarifies/explains; injection scenario 11; fallback badge |
| Security & governance | Signed requirements, merchant-signed data, 409, specific exceptions, no secrets |
| "Customer concern → solution" | Evidence packet = "who's responsible?"; HOLD = "layovers I don't want" |
