# Mastercard Verifiable Intent (VI) SDK — how we use it

Repo: https://github.com/agent-intent/verifiable-intent · Docs: https://verifiableintent.dev · License: **Apache-2.0** · Status: draft v0.1 (spec dated 2026-02-18; last commit we checked: 2026-04-20) · Python ≥3.10 · only dependency: `cryptography`.
We cloned it and ran `examples/autonomous_flow.py` and `examples/constraint_checking.py` successfully ("Chain valid: True", "Constraints satisfied: True").

## Install
```bash
pip install "verifiable-intent @ git+https://github.com/agent-intent/verifiable-intent.git"
# or clone and: pip install -e ./verifiable-intent
```
Package import name: `verifiable_intent`. The `examples/` folder is NOT part of the package — copy what you need from `examples/helpers.py` into `app/vi_adapter.py` (keep an Apache-2.0 attribution comment).

## Mental model: 3 layers (SD-JWT credentials)
| Layer | Signed by | Contains | Our use |
|---|---|---|---|
| **L1** issuer credential | Issuer (e.g., Mastercard/bank) | Binds the user's public key (`cnf.jwk`), `pan_last_four`, scheme | Fixture identity for "Alex Traveler" (synthetic) |
| **L2** user mandate (Autonomous mode) | **User** key | `prompt_summary` (optional), **checkout mandate** `vct: mandate.checkout.open.1` with `constraints[]` + agent key `cnf`, **payment mandate** `vct: mandate.payment.open.1` with constraints | We put the traveler-**approved** requirements here as a custom constraint, plus amount range + allowed merchants |
| **L3a** final payment / **L3b** final checkout | **Agent** key | L3b: `checkout_jwt` (**merchant-signed** cart), `checkout_hash`, optional `line_items`, `prompt_summary`. L3a: `payment_amount`, `payee`, `transaction_id` (== `checkout_hash`) | The merchant's signed itinerary lives in `checkout_jwt` |

Modes: **Immediate** (2 layers; user confirms final cart) vs **Autonomous** (3 layers; user sets constraints, agent acts). We use **Autonomous**.

## Key public API (from `verifiable_intent/__init__.py`)
- Issuance: `create_layer1(cred, issuer_private_key)`, `create_layer2_autonomous(user_mandate, user_private_key)`, `create_layer3_checkout(...)`, `create_layer3_payment(...)`
- Models: `IssuerCredential`, `UserMandate`, `MandateMode`, `CheckoutMandate`, `PaymentMandate`, `Constraint` (base, preserves unknown types via `extra_fields`), `PaymentAmountConstraint(currency, min, max)` (integer cents), `AllowedMerchantConstraint(allowed=[...])`, `AllowedPayeeConstraint`, `CheckoutLineItemsConstraint`, `parse_constraint`
- Verification: `verify_chain(l1, l2, l3_payment=..., l3_checkout=..., issuer_public_key=..., l1_serialized=..., l2_serialized=..., ...) -> ChainVerificationResult(.valid, .errors, .l3_payment_claims, ...)`, `check_constraints(constraints, fulfillment, mode=StrictnessMode.PERMISSIVE, is_open_mandate=False, constraint_policy=None) -> ConstraintCheckResult(.satisfied, .violations, .checked, .skipped)`, `verify_checkout_hash_binding`, `verify_l3_cross_reference`
- Crypto: `verifiable_intent.crypto.sd_jwt.decode_sd_jwt`, `resolve_disclosures`; `verifiable_intent.crypto.signing.es256_sign / es256_verify / public_key_to_jwk / jwk_to_public_key / _jwt_encode / _jwt_decode_parts` (underscore = internal; fine for a prototype)

## Recommended approach (incremental — do not rewrite from scratch)
1. **Run the example first:** `python verifiable-intent/examples/autonomous_flow.py`. Read it top to bottom; it is the template.
2. **Copy into `app/vi_adapter.py`:** the deterministic demo key pairs (`_key_from_d`, `get_issuer_keys/get_user_keys/get_agent_keys/get_merchant_keys` — demo keys, NOT secret), `create_checkout_jwt` pattern, `checkout_hash_from_jwt`, and the step sequence from `autonomous_flow.main()`.
3. **Swap the tennis racket for flights:**
   - `prompt_summary` = traveler's original text (informational only).
   - `MERCHANTS` = synthetic airlines/OTAs, e.g. `{"id":"merchant-skyways","name":"SkyWays Air","website":"https://skyways.example"}`.
   - Payment mandate `PaymentAmountConstraint(currency="USD", min=0, max=approved.max_total_cents)`.
   - Checkout mandate constraints: `AllowedMerchantConstraint(allowed=MERCHANTS)` **plus our custom constraint** (below). If issuance requires `CheckoutLineItemsConstraint`/`acceptable_items` (the example uses them), set `acceptable_items` to the candidate offer ids from fixtures — keep it simple.
4. **Merchant-signed offer:** build a `checkout_jwt` whose payload carries the itinerary (schema below), signed with the merchant key (ES256). Its hash becomes `checkout_hash` / `transaction_id`.
5. **Verify** with `verify_chain(...)` exactly as the example does (merchant side with L3b, network side with L3a). Then **verify the merchant signature on `checkout_jwt`** yourself (`_jwt_decode_parts` → `es256_verify(signing_input, sig, merchant_public_key)`) and only then parse the itinerary from its payload into `FlightOffer`.
6. Run VI's own `check_constraints(payment_constraints, fulfillment)` for amount/payee (registered types). Our custom type is **skipped** by VI in PERMISSIVE mode — that's expected; **our `rules_engine` evaluates it**. Do NOT pass `is_open_mandate=True` (it rejects unknown types).

## Our custom constraint (spec-compliant per constraints.md §6.1, "Model B" private naming)
```python
from verifiable_intent import Constraint
flight_req = Constraint(
    type="urn:intent-judge:requirements",
    extra_fields={
        "category": approved.category,  # "flight" for the demo; the constraint type is category-neutral
        "requirement_set_id": approved.requirement_set_id,
        "origin_airports": approved.origin_airports,
        "destination_airports": approved.destination_airports,
        "depart_date": approved.depart_date.isoformat(),
        "depart_window": approved.depart_window and approved.depart_window.model_dump(),
        "arrive_by": approved.arrive_by and approved.arrive_by.isoformat(),
        "max_stops": approved.max_stops,
        "max_total_cents": approved.max_total_cents,
        "currency": approved.currency,
        "cabin": approved.cabin,
        "refundable_required": approved.refundable_required,
        "passengers": approved.passengers,
        "approved_at": approved.approved_at.isoformat(),
    },
)
```
Spec rules: custom types MUST have a `type` field, MUST use collision-resistant naming (URN/reverse-DNS), and parsers MUST preserve all fields. Roadmap: propose a registered `mandate.checkout.*` type (e.g., `mandate.checkout.travel_itinerary`).
**Verified on Oct 12:** adding this `Constraint(...)` to the checkout mandate in `examples/autonomous_flow.py` still yields "Chain valid: True" and "Constraints satisfied: True"; `check_constraints` reports it under `skipped` (PERMISSIVE), as intended.

Because L2 is signed by the **user** key, the approved requirements are tamper-evident: the agent cannot silently drop "nonstop."

## Merchant `checkout_jwt` payload for a flight (our schema; VI says checkout_jwt schema is implementation-defined, SHOULD include item ids, quantities, prices, currency, merchant id)
```json
{
  "iss": "https://skyways.example",
  "sub": "cart_checkout",
  "iat": 1791820000, "exp": 1791823600,
  "merchant": {"id": "merchant-skyways", "name": "SkyWays Air"},
  "cart": {
    "items": [{
      "sku": "OFFER-B-3STOP",
      "type": "air_itinerary",
      "quantity": 1,
      "passengers": 1,
      "cabin": "economy",
      "refundable": false,
      "segments": [
        {"carrier":"SW","flight_number":"SW101","from":"JFK","to":"PHL","depart_local":"2026-10-20T06:05:00-04:00","arrive_local":"2026-10-20T07:10:00-04:00"},
        {"carrier":"SW","flight_number":"SW233","from":"PHL","to":"ATL","depart_local":"2026-10-20T08:30:00-04:00","arrive_local":"2026-10-20T10:40:00-04:00"},
        {"carrier":"SW","flight_number":"SW410","from":"ATL","to":"CLT","depart_local":"2026-10-20T11:50:00-04:00","arrive_local":"2026-10-20T13:05:00-04:00"},
        {"carrier":"SW","flight_number":"SW588","from":"CLT","to":"MCO","depart_local":"2026-10-20T14:20:00-04:00","arrive_local":"2026-10-20T16:05:00-04:00"}
      ]
    }],
    "total": {"amount_cents": 28000, "currencyCode": "USD", "includes_taxes_and_fees": true}
  }
}
```
Rule: the rules engine reads ONLY from this verified payload. If a field is absent (e.g., no `refundable`), it is `None` → `missing` when required.

## Gotchas
- Money is **integer minor units** everywhere in VI (27999 = $279.99).
- Timestamps `iat/exp` are epoch seconds; keep L2 expiry ≥ demo duration (example uses 24h).
- `checkout_hash = B64U(SHA-256(ASCII(checkout_jwt)))` and MUST equal L3a `transaction_id`.
- Selective disclosure: merchant sees checkout side, network sees payment side — follow the example's `build_role_presentations` / `verify_chain` calls.
- Never present demo keys as real; label them "demo keys" in UI/debug output.
