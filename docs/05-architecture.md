# Architecture

## Components
```
web/ (static page)  ──HTTP──▶  app/main.py (FastAPI)
                                 ├─ foundry_client.py   (LLM: extract+clarify, explain, evidence narrative; MOCK_LLM fallback)
                                 ├─ vi_adapter.py       (Mastercard VI SDK: keys, L1/L2/L3, merchant checkout JWT, verify)
                                 ├─ rules_engine.py     (deterministic PASS/HOLD/BLOCK — the only decider)
                                 ├─ evidence.py         (assemble evidence packet; responsibility recommendation table)
                                 ├─ store.py            (in-memory dicts: requirement sets, offers, decisions, exceptions, purchases)
                                 └─ fixtures/*.json     (synthetic offers & scenarios)
```

## Suggested files
```
app/__init__.py
app/main.py              # FastAPI app, routes, serves web/
app/models.py            # Pydantic models (below)
app/rules_engine.py      # evaluate(requirements, offer) -> Decision
app/vi_adapter.py        # build_l1(), build_l2(requirements), merchant_sign_offer(offer), build_l3(), verify(...)
app/foundry_client.py    # extract_requirements(text), explain(decision), evidence_narrative(packet)
app/evidence.py          # build_packet(...), recommend_responsibility(...)
app/store.py
app/fixtures/offers.json # merchant flight offers (see 10-test-plan.md)
web/index.html, web/app.js, web/styles.css
tests/...
.env.example
requirements.txt         # fastapi, uvicorn[standard], pydantic>=2, openai, python-dotenv, pytest, httpx,
                         # verifiable-intent @ git+https://github.com/agent-intent/verifiable-intent.git
```

## Data models (Pydantic)
```python
class ApprovedRequirements(BaseModel):
    requirement_set_id: str
    category: str = "flight"               # demo category; contract is category-neutral (Plan 3)
    origin_airports: list[str]            # e.g. ["JFK","LGA","EWR"]  (required)
    destination_airports: list[str]       # e.g. ["MCO","TPA"]         (required)
    depart_date: date                     # required
    depart_window: TimeWindow | None      # {"earliest":"06:00","latest":"12:00"}
    arrive_by: time | None
    max_stops: int | None                 # 0 = nonstop
    max_total_cents: int                  # all-in price incl. taxes/fees (required)
    currency: str = "USD"
    cabin: Literal["economy","premium_economy","business","first"] | None
    refundable_required: bool | None
    passengers: int = 1
    source_text: str                      # traveler's original words (for evidence only)
    approved_by_traveler: bool
    approved_at: datetime

class Segment(BaseModel):
    carrier: str; flight_number: str
    from_airport: str; to_airport: str
    depart_local: datetime; arrive_local: datetime

class FlightOffer(BaseModel):            # extracted ONLY from the verified merchant checkout_jwt
    offer_id: str
    merchant_id: str; merchant_name: str
    segments: list[Segment]
    total_cents: int | None               # None => missing
    currency: str
    cabin: str | None
    refundable: bool | None
    passengers: int | None
    offer_hash: str                       # B64U(SHA-256(checkout_jwt)) == VI checkout_hash

class CheckResult(BaseModel):
    check_id: Literal["ORIGIN","DESTINATION","DATE","DEPART_WINDOW","ARRIVE_BY","STOPS",
                      "PRICE","CURRENCY","CABIN","REFUNDABLE","PASSENGERS"]
    requirement: str; offer_value: str
    status: Literal["pass","fail","missing","not_required"]
    message: str                           # plain English

class Decision(BaseModel):
    decision_id: str; requirement_set_id: str; offer_hash: str
    result: Literal["PASS","HOLD","BLOCK"]
    vi_chain_valid: bool; merchant_signature_valid: bool
    checks: list[CheckResult]
    explanation: str | None               # from LLM; display only, never used for logic
    created_at: datetime

class ExceptionAcceptance(BaseModel):
    decision_id: str; offer_hash: str
    check_id: str; accepted_value: str
    traveler_statement: str               # e.g. "I accept 3 connections on this itinerary"
    accepted_at: datetime

class EvidencePacket(BaseModel):
    purchase_id: str; dispute_claim: str
    vi_chain_valid: bool; merchant_signature_valid: bool
    approved_requirements: ApprovedRequirements
    merchant_offer: FlightOffer
    checks: list[CheckResult]
    exceptions: list[ExceptionAcceptance]
    suggested_reason_code: Literal["4837","4853","none"]
    recommended_responsibility: Literal["traveler","agent_platform","merchant","fraud_path","unclear"]
    rationale: str
    narrative: str | None                 # LLM-written summary; display only
    final_decision: Literal["dispute analyst"] = "dispute analyst"
```

## API
| Method & path | Body | Returns | Notes |
|---|---|---|---|
| `GET /api/scenarios` | — | list of demo scenarios | from fixtures |
| `POST /api/intent/extract` | `{text}` | `{draft_requirements, questions[]}` | LLM (or mock). Draft is NOT approved |
| `POST /api/intent/approve` | `{draft_requirements, answers}` | `{requirement_set_id, vi_l2_summary}` | Creates ApprovedRequirements, builds L1/L2 with custom constraint |
| `POST /api/check` | `{requirement_set_id, offer_id}` | `Decision` | Merchant signs offer → L3 → verify → rules engine → explanation |
| `POST /api/exceptions` | `{decision_id, check_ids[], traveler_statement}` | updated decision state | Only for checks with status fail/missing |
| `POST /api/purchase` | `{decision_id}` | `201 {purchase_id}` or **`409`** | **Enforcement:** PASS, or all fail/missing checks excepted for same offer_hash; BLOCK never purchasable |
| `POST /api/disputes` | `{purchase_id, claim}` | `EvidencePacket` | Deterministic responsibility table + optional LLM narrative |

## Sequence (happy-path HOLD demo)
```
Traveler text → /intent/extract (LLM) → questions → traveler answers → /intent/approve
  → VI L1 (issuer) + L2 (user signs constraints incl. urn:intent-judge:requirements)
Agent picks offer → merchant signs checkout_jwt (itinerary) → agent builds L3a/L3b
  → /check: verify_chain + merchant signature → extract offer from signed payload
  → rules_engine.evaluate → HOLD (STOPS fail) → LLM explains → UI shows hold
Traveler cancels (or accepts exception) → /purchase enforces → (later) /disputes → evidence packet
```

## Environment
`.env.example`:
```
AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com/
AZURE_OPENAI_API_KEY=<from Foundry portal; never commit>
AZURE_OPENAI_DEPLOYMENT=<your deployment name, e.g. gpt-4o-mini>
AZURE_OPENAI_API_VERSION=2024-10-21
MOCK_LLM=0
```
Run: `uvicorn app.main:app --reload` → open http://localhost:8000
