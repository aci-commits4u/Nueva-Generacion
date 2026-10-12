# Rules engine spec (`app/rules_engine.py`) — the only component that decides

Pure Python. No network. No LLM. 100% unit-tested.

## Signature
```python
def evaluate(req: ApprovedRequirements, offer: FlightOffer,
             vi_chain_valid: bool, merchant_signature_valid: bool) -> Decision
```

## Order of evaluation
1. If `not vi_chain_valid` or `not merchant_signature_valid` → **BLOCK** (fraud path). Still return checks list (may be empty) and a clear message. BLOCK can never be purchased or excepted.
2. If `not req.approved_by_traveler` → **HOLD** with a single check `APPROVAL` missing ("Requirements not approved by traveler").
3. Run every check below. Each returns `pass | fail | missing | not_required`.
4. Result: **PASS** iff every check is `pass` or `not_required`. Otherwise **HOLD**.

## Derived values from the offer
- `stops = len(segments) - 1` (a connection = a stop for our purposes; document this in UI as "connections").
- `first = segments[0]`, `last = segments[-1]`; empty segments → all itinerary checks `missing`.
- Departure date/time = `first.depart_local` (local time as given). Arrival = `last.arrive_local`.

## Checks
| check_id | Required? | Logic | fail message example |
|---|---|---|---|
| ORIGIN | always (req field required) | `first.from_airport in req.origin_airports` | "Departs from EWR; you approved JFK or LGA." |
| DESTINATION | always | `last.to_airport in req.destination_airports` | "Arrives at FLL; you approved MCO or TPA." |
| DATE | always | `first.depart_local.date() == req.depart_date` | "Departs Oct 21; you approved Oct 20." |
| DEPART_WINDOW | if `req.depart_window` | earliest ≤ depart time ≤ latest | "Departs 6:05 PM; you approved 6:00 AM–12:00 PM." |
| ARRIVE_BY | if `req.arrive_by` | `last.arrive_local.time() <= req.arrive_by` (same day as depart_date; if arrives next day → fail) | "Arrives 4:05 PM; you approved arrival by 2:00 PM." |
| STOPS | if `req.max_stops is not None` | `stops <= req.max_stops` | "You asked for nonstop. This itinerary has 3 connections." |
| PRICE | always | `offer.total_cents` present and `<= req.max_total_cents`; offer total must include taxes/fees (if payload says not included → `missing`) | "Total $312.40; you approved up to $300.00." |
| CURRENCY | always | `offer.currency == req.currency` | "Priced in EUR; you approved USD." |
| CABIN | if `req.cabin` | equal (case-insensitive) | "Basic economy; you approved economy." *(treat basic_economy ≠ economy)* |
| REFUNDABLE | if `req.refundable_required is True` | `offer.refundable is True` | "Non-refundable fare; you required refundable." |
| PASSENGERS | always | `offer.passengers == req.passengers` | "Booked for 2 passengers; you approved 1." |

**Missing rule:** if the requirement applies and the offer field needed is `None`/absent → status `missing`, message "The merchant offer doesn't state X, so we can't confirm your requirement." → contributes to HOLD.

## Exceptions
```python
def can_purchase(decision: Decision, exceptions: list[ExceptionAcceptance]) -> tuple[bool, str]
```
- `BLOCK` → False ("blocked: credential or merchant signature invalid").
- `PASS` → True.
- `HOLD` → True only if **every** check with status `fail` or `missing` has an `ExceptionAcceptance` with matching `decision_id`, `offer_hash`, `check_id`. Otherwise False, listing the uncovered checks.
- Exceptions for an old `offer_hash` never apply to a new offer (offers can change price/segments).
- `APPROVAL` missing cannot be excepted (traveler must approve requirements instead).

## Enforcement at the API
`POST /api/purchase` calls `can_purchase`. If False → **HTTP 409** with `{reason, uncovered_checks}`. There is no other code path that creates a purchase. Add a test that tries to purchase a HOLD without exceptions and expects 409; and one that supplies an LLM explanation saying "approved" and still expects 409 (LLM text has no authority).

## Responsibility recommendation (used by `evidence.py`, deterministic)
| Evidence | recommended_responsibility | suggested_reason_code |
|---|---|---|
| VI chain or merchant signature invalid | `fraud_path` | 4837 |
| Purchase made on PASS, traveler disputes a requirement that **was approved and passed** | `traveler` (purchase matched approved requirements) | none (dispute likely invalid) |
| Traveler disputes something **never in approved requirements** (e.g., "I wanted nonstop" but max_stops was not set) | `traveler` | none |
| Purchase made with a recorded exception for the disputed check | `traveler` (informed consent on record) | none |
| A check that should have failed was bypassed (shouldn't happen; e.g., purchase outside our flow) or agent submitted an offer different from the merchant-signed one | `agent_platform` | 4853 |
| Merchant-signed offer contradicts what the merchant actually delivered (e.g., signed nonstop, flew 3 stops) | `merchant` | 4853 |
| Insufficient evidence | `unclear` | none |
Always add `rationale` (one sentence) and `final_decision: "dispute analyst"`.

## Unit tests to write first (`tests/test_rules_engine.py`)
- nonstop approved + nonstop offer → PASS
- nonstop approved + 3-connection offer → HOLD, STOPS fail, message mentions "3 connections"
- max_stops None + 1 connection → PASS (STOPS not_required)
- price over by $0.01 → HOLD
- offer total missing → HOLD (PRICE missing)
- refundable required + refundable None → HOLD (missing)
- wrong date, wrong origin, wrong destination, window violation, arrive-by violation → HOLD each
- vi_chain_valid False → BLOCK
- can_purchase: HOLD + exceptions covering all → True; covering some → False; wrong offer_hash → False; BLOCK → False
