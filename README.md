# Intent Judge

**Production demo: [intent-judge-perfected.vercel.app](https://intent-judge-perfected.vercel.app)** · Branch: `production`

**Development instance: [intent-judge-perfected-dev.vercel.app](https://intent-judge-perfected-dev.vercel.app)** · Branch: `develop`

The development checkout is `/Users/victor/Nueva-Generacion-dev`; the existing
release checkout is `/Users/victor/Nueva-Generacion`. Both release branches
start from accepted snapshot `d6f8131`. The production project is
`intent-judge-perfected` (`prj_sQQGLWLVZ7qigP9WePx9fIH5kzWT`) and the separate
development project is `intent-judge-perfected-dev`
(`prj_BQgv2BqYWbrJjqW0LkPw13cVC8jc`).

A live AI interpretation layer for agentic commerce. Translate a request into customer-reviewed requirements, bind them into Mastercard's open-source Verifiable Intent SDK, and check merchant-signed offers with deterministic domain rules.

The model never approves a purchase. The demo uses synthetic merchants, signing identities, inventory, and simulated payments.

## Demo

1. Choose Flight, Hotel, or General and enter a request. Live Microsoft Foundry is the default.
2. Continue the conversation while the intent summary updates. Review the captured rules, source quotations, and explicit no preferences before approval.
3. Approve the exact reviewed requirements. For flights, optionally search current Kiwi options through the read-only live discovery panel; outbound links open on Kiwi.
4. Compare the live external quotes with two merchant-signed synthetic offers. Demonstrate a refused purchase, or accept a specific difference tied to the exact offer hash.
5. Confirm a simulated booking, download signed evidence, and prepare an analyst review.

Start with: “Book me a nonstop flight from EWR to MCO on 2026-11-12 under $300.” The $295 nonstop offer matches; the $280 connecting offer satisfies the native budget but is held by the approved nonstop requirement.

Kiwi discovery is flight-only, read-only, and unsigned. Its quotes and booking links never approve, purchase, or replace the signed-offer check. Hotels and General use the shared intent layer with synthetic signed offers; they do not have live shopping integrations. Domain adoption is configuration-driven for supported operators; arbitrary predicates still need reviewed semantics and trusted facts.

The live flight search is deliberately separate from the Verifiable Intent demo
flow. Kiwi supplies external observations; the synthetic merchant adapter
supplies the signed checkout facts used for deterministic enforcement, simulated
purchase, and evidence. This keeps live shopping useful without treating an
unsigned quote as proof.

## Run locally

```sh
uv venv --python 3.12
uv pip install -r requirements-dev.txt
cp .env.example .env
.venv/bin/uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000. Configure Azure variables for live AI. For a disconnected demonstration set `MOCK_LLM=1` and deliberately select **Emergency offline parser** in the interface. The app never silently switches modes.

```sh
.venv/bin/pytest -q
.venv/bin/python scripts/live_probe.py  # explicit paid provider evaluation
```

## Architecture

- `app/rules_engine.py`: pure typed deterministic checks; missing facts hold checkout.
- `profiles/`: versioned flights, hotels, and limited general-mode schemas.
- `app/vi_adapter.py`: pinned VI SDK L1/L2/split L3 issuance and verification; independent ES256 merchant verification; explicit dispatch of every constraint.
- `app/main.py`: server-owned review, approval, exact exceptions, reauthorization, idempotent purchase, evidence, and session recovery.
- `app/ai_pipeline.py`: two-stage adaptive planning on Foundry gpt-oss-120b, with strict grounded output validation and one bounded read-only tool action.
- `app/structured_intent.py`: strict provider schema and exact customer-source references, hydrated before semantic validation.
- `app/adaptive_intent.py`: shared action, criterion, question, and merchant-context contract across domains.
- `app/conversation.py`: revision-bound state, exact question binding, customer corrections, and approval preparation.
- `app/quality.py`: authenticated, replay-safe daily live canary and public synthetic quality reports.
- `app/foundry_client.py`: original baseline and on-demand explanation, without purchase authority.
- `app/store.py`: SQLite locally; Azure Table conditional writes on Vercel. Function memory is not authoritative.
- `app/shopping_provider.py`: bounded, read-only Kiwi MCP flight discovery with normalized external quotes and allowlisted outbound booking URLs; it cannot issue signed facts or purchase.
- `demo/`: separate synthetic commerce adapter. Replacing search/payment does not replace intent enforcement.
- `web/`: static vanilla HTML, JS, and CSS served by FastAPI; the live flight panel is `web/views/shopping.js`; no frontend build step.

Hosted deployments require stable environment signing keys and durable Azure storage. Development sessions use `IntentJudgeDev` and production sessions use `IntentJudge`; each project has distinct signing keys, while the global AI money/call reservation ledger is shared through the budget table. Never use ephemeral keys or SQLite for Vercel. Keys are demonstration trust anchors, not Mastercard credentials or consumer hardware signatures.

GitHub Actions is a CI gate only. Vercel uploads are manual and require the
clean-tree, exact-commit, green-CI manifest from
[`scripts/prepare_deployment.py`](scripts/prepare_deployment.py). There is no
automatic production deploy or branch protection configured. Feature work
starts from `develop`, is tested in the development instance, and reaches
`production` only through explicit review and promotion.

## Verification and scope

See [implementation status](docs/implementation-status.md), [design decisions](DESIGN.md), and the [research index](docs/00-index.md).

The current live AI path is adaptive: it can ask a model-generated question, retrieve read-only merchant context, inspect synthetic offers, or stop for customer review. The model remains advisory; approval and checkout are deterministic. The first three fresh adaptive live cases strict-passed 1/3 before the current fixes, and that raw artifact remains unchanged. See [the adaptive engine contract](docs/19-adaptive-intent-engine.md) and [running product and operations](docs/11-running-product.md) for the evidence boundary and controls.

This is a showable student prototype. It can perform read-only live flight
discovery through Kiwi and open outbound Kiwi booking links, but it does not
execute a booking, take payment, file chargebacks, establish legal liability,
or guarantee perfect intent extraction. Its signed checkout, simulated
purchase, and evidence path remain synthetic. It implements the supported
profile fields; unimplemented requirements stay held.

The upstream draft checker does not natively support our custom constraint. We verify the original chain, evaluate supported native constraints strictly, dispatch our recognized custom constraint to the deterministic engine, and hold any unimplemented constraint. We do not claim stock SDK or payment-network compatibility for the extension.

See [AI evaluation and conversation](docs/15-ai-evaluation-and-conversation.md) for experimental results, known failures, the daily canary, and budget limits. The Quality view shows recorded results; none of these results guarantee complete intent understanding.

The product now starts with an overview and a **Show me how** walkthrough. Read [the tutorial guide](docs/16-product-walkthrough.md) for the five stages and working demo controls. The tutorial makes no paid model calls; **Try the demo** opens the actual Foundry workflow.

The [route-choice incident and repair](docs/21-route-choice-reliability.md)
records the London→Toronto failure, role-scoped global airport choices,
source-linked corrections, explicit saved-conversation refresh, and the
separate regression and native acceptance evidence.

[Messy live user testing](docs/22-messy-user-testing.md) records unfamiliar
flight and hotel requests typed into the deployed chatbot, the observed
failures, model repairs, hotel clarification retention, and the final live
flight purchase with signed evidence. It keeps
real model behavior separate from offline regressions and harness failures.

The [source-reference contract](docs/23-source-reference-contract.md) explains
the measured model changes, strict structured output, and the distinction
between proving where a requirement came from and understanding it correctly.
