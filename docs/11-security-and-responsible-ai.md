# Security & Responsible AI

Kit test: *"Can your team explain how the solution protects the customer — not just what it does?"*

## Our answer in one breath
"The AI never approves anything. The traveler approves their own requirements, Mastercard's Verifiable Intent signs them, code checks them against the merchant-signed offer, any gap holds the purchase, and a human makes every dispute call — all on synthetic data."

## Controls in the prototype (live)
| Area | Control |
|---|---|
| Decision authority | Only `rules_engine.py` decides; LLM output is display-only; `/api/purchase` enforces with 409 |
| Data integrity | User-signed L2 (approved requirements), merchant-signed checkout_jwt, VI chain verification; tampering → BLOCK |
| Consent | Explicit approval of requirement list; exceptions record check, value, offer hash, timestamp |
| Missing info | Missing = HOLD (never assume) |
| Prompt injection | All traveler/merchant text passed as JSON data; system prompts instruct to ignore embedded instructions; rules engine never reads free text; tested (scenario 11) |
| Transparency | Every HOLD lists the exact requirement and offer value; AI text labeled "AI-generated explanation" |
| Fairness | Decisions depend only on requirements vs offer fields; no traveler identity/attributes used |
| Data | Synthetic only; no PII; demo keys labeled as demo; no secrets in repo/logs/slides |
| Resilience | `MOCK_LLM=1` offline mode; recorded backup video |

## Production considerations (designed, not built — say so)
- **Microsoft Entra ID**: identities for analysts/admins and managed identity for the service; least privilege.
- **Azure Key Vault**: model keys and signing keys; never in code.
- **Azure AI Content Safety**: optional input filter on traveler free text (only mention if implemented).
- **Logging/audit**: decision ids, check results, exception records; no card data or personal data in logs.
- Pilot governance: false-hold rate and dispute outcomes reviewed by a named owner.
(Purview, Defender, Azure Policy: don't list unless asked; if asked, explain their specific job.)

## Limitations to state honestly (judges reward this)
- Natural-language extraction can be wrong → that's why the traveler approves the list before anything is checked.
- We only check what was approved; unstated preferences aren't enforced (by design).
- "Intent-checked" is our label; liability protection would require Mastercard network rules.
- Prototype on synthetic data; no live payments or dispute systems.
- Recommendations of responsibility are advisory; analysts decide.

## Threat model (short)
| Threat | Mitigation |
|---|---|
| Agent drops/changes a requirement | Requirements signed by user in L2; agent can't alter without breaking signature |
| Agent misrepresents offer | We only read merchant-signed checkout_jwt |
| Forged merchant offer | Merchant signature verification; failure → BLOCK |
| Model manipulated to "approve" | Model has no approval power; enforcement in code |
| Replay of exception on a changed offer | Exceptions bound to offer_hash |
