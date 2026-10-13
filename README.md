# Intent Judge

**Live demo: [intent-judge-perfected.vercel.app](https://intent-judge-perfected.vercel.app)** · Branch: `victor/perfected`

A live AI interpretation layer for agentic commerce. Translate a request into customer-reviewed requirements, bind them into Mastercard's open-source Verifiable Intent SDK, and check merchant-signed offers with deterministic domain rules.

The model never approves a purchase. The demo uses synthetic merchants, signing identities, inventory, and simulated payments.

## Demo

1. Choose Flight, Hotel, or General and enter a request. Live Microsoft Foundry is the default.
2. Continue the conversation while the intent summary updates. Review the captured rules, source quotations, and explicit no preferences before approval.
3. Approve the exact reviewed requirements. Compare two merchant-signed synthetic offers.
4. Demonstrate a refused purchase, or accept a specific difference tied to the exact offer hash.
5. Confirm a simulated booking, download signed evidence, and prepare an analyst review.

Start with: “Book me a nonstop flight from EWR to MCO on 2026-11-12 under $300.” The $295 nonstop offer matches; the $280 connecting offer satisfies the native budget but is held by the approved nonstop requirement.

Hotel uses the same engine with a different reviewed JSON profile. General mode preserves unsupported conditions and holds checkout. Domain adoption is configuration-driven for supported operators; arbitrary predicates still need reviewed semantics and trusted facts.

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
- `app/ai_pipeline.py`: measured extraction + independent coverage audit on Foundry gpt-oss-120b, with strict grounded output validation.
- `app/conversation.py`: revision-bound conversation and ranked profile questions.
- `app/quality.py`: authenticated, replay-safe daily live canary and public synthetic quality reports.
- `app/foundry_client.py`: original baseline and on-demand explanation, without purchase authority.
- `app/store.py`: SQLite locally; Azure Table conditional writes on Vercel. Function memory is not authoritative.
- `demo/`: separate synthetic commerce adapter. Replacing search/payment does not replace intent enforcement.
- `web/`: static vanilla HTML, JS, and CSS served by FastAPI; no frontend build step.

Hosted deployments require stable environment signing keys and durable Azure storage. Never use ephemeral keys or SQLite for Vercel. Keys are demonstration trust anchors, not Mastercard credentials or consumer hardware signatures.

## Verification and scope

See [implementation status](docs/implementation-status.md), [design decisions](DESIGN.md), and the [research index](docs/00-index.md).

The conversational revision has 76 passing regression tests, measured three pipelines on 12 development cases, and passed 6/6 untouched holdout cases with the selected audited pipeline. It completed live desktop/mobile Foundry flows, including the actual purchase refusal, exact consent and signed evidence download. Follow [the two-minute demo script](docs/12-demo-script.md); [running product and operations](docs/11-running-product.md) records the real endpoints and budget controls.

This is a showable student prototype. It does not perform real travel search, take payment, file chargebacks, establish legal liability, or guarantee perfect intent extraction. It implements the supported profile fields; unimplemented requirements stay held.

The upstream draft checker does not natively support our custom constraint. We verify the original chain, evaluate supported native constraints strictly, dispatch our recognized custom constraint to the deterministic engine, and hold any unimplemented constraint. We do not claim stock SDK or payment-network compatibility for the extension.

See [AI evaluation and conversation](docs/15-ai-evaluation-and-conversation.md) for experimental results, known failures, the daily canary, and budget limits. The Quality view shows real recorded results.

The product now starts with an overview and a **Show me how** walkthrough. Read [the tutorial guide](docs/16-product-walkthrough.md) for the five stages and working demo controls. The tutorial makes no paid model calls; **Try the demo** opens the actual Foundry workflow.
