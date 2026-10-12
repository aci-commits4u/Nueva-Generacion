# LEAD ASPIRE — event rules and judging

**Event:** LEAD ASPIRE, Oct 12, 2026, 9:00 AM–4:00 PM, New York City. Teams of 4–6 students act as **Microsoft Cloud & AI Specialists for a day** for client **Mastercard**. Hosted with **HOLA (Hispanic & Latinx at Microsoft)**. Strategy reviewed by **EY** partners. GitHub and Microsoft volunteers on site.

Flow: **DISCOVER → STRATEGIZE → BUILD → PITCH**.

## Ground rules (kickoff slide)
- "In this competition, you work for Microsoft." Build must use Microsoft tech; **an agent built in Azure AI Foundry** (instructions provided by the event).
- **GitHub Copilot** encouraged; GitHub volunteers present.
- Microsoft staff guide but **won't solve technical issues**.
- Resources are optional but highly encouraged; judges look for the kit's type of thinking.
- "It's not about who moves faster, it's about who asks the best questions."

## Phase 1 — Discover (done)
Waves of 3 teams, 10 minutes per session. Open, evidence-seeking questions; listen > talk; capture quotes, numbers, workarounds. Output: Problem Insight sentence.

## Phase 2 — Strategize (done, approved)
Opportunity Mapping Board (digital whiteboard, 8 boxes + Executive Solution Map screenshot), SOW template (formatting unchanged), ~3-minute EY partner review. **Result: approved.** SOW is not submitted anywhere.

## Phase 3 — Build (now)
### Official Foundry setup (event guide)
1. azure.microsoft.com/free/students (Azure for Students, no card)
2. Search **Foundry** → Create (resource group e.g. `lead`) → name project → Review + create (a few minutes)
3. **Go to Foundry portal** → **Test in playground** → **Create your own agent**

### GitHub Copilot
Student Pack approval can take hours and benefits up to 72h → use **Copilot Free** today.

### Build Readiness Checklist (official — all must be true before Pitch)
- **Core experience:** main user journey works end to end
- **Discovery alignment:** still addresses what we heard
- **Scope discipline:** the critical experience, not many unfinished features
- **Real functionality:** we know what is fully working, partial, mocked, or simulated
- **AI behavior:** tested different inputs; understand key limitations
- **Error handling:** failed inputs, connections, components considered
- **Data & security:** appropriate demo data; no secrets/credentials/sensitive info exposed
- **Dependencies:** required APIs/services/environments working
- **Demo path:** exact flow known; each part has an owner
- **Backup plan:** fallback for critical demo moments
- **Customer concern → solution mapping:** every major Discovery concern traced to the part of the solution that addresses it, or marked out of scope ("Build with traceability")

### Security & Governance review (official)
Identity · Permissions (least privilege for users, services, agents) · Secrets (never in code or prompts) · Data · Privacy · Encryption · Logging (no secrets in logs) · Failure (AI wrong/compromised) · AI guardrails (scope, limits, human oversight) · Ownership · Governance · Demo safety.
Test: *"Can your team explain how the solution protects the customer — not just what the solution does?"*
Microsoft examples the kit names: Entra (identity), Purview (data governance), Defender for Cloud, Azure Policy, Key Vault (secrets), Foundry (AI safety & evaluation). Principle: "Use products to implement the security decision — not to replace the decision."

## Phase 4 — Pitch & Submit
- Submit **deck + demo link (optional)**. **5 minutes** presenting + **2 minutes** Q&A.
- Story: **Hook → Problem → Discovery insight → Solution → Demo → Impact.** If they remember 3 things: the problem, our recommendation, the value.
- Slides: one idea per slide; **headlines = conclusions**; show don't transcribe; numbers with context; remove extras.
- Demo: set the scene → realistic input from Discovery → show the change → show the outcome (before vs after). Safe demo data; be transparent about live/mocked; backups for critical dependencies.
- Present as a team: start immediately, no apologies, purposeful handoffs, plain language, close together.
- Q&A: listen fully → **Answer → Evidence → Tradeoff/limitation → What we'd do next**.
- Final reminder: *"You are not pitching the technology. You are pitching why this solution should exist."*
