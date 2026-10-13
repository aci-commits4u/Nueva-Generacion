# Reusable domain profiles

Status: proposed contract. This is the method for adapting the AI intake and deterministic checks without rebuilding the application.

## What a profile contains

1. Stable ID, semantic version, content digest, and domain label.
2. A typed requirement schema and explicit field states.
3. Clarification priorities, question text, choices, and explanations for normalization.
4. Allowed operators and references to approved derivations.
5. A schema for verified merchant facts, field mappings, and provenance requirements.
6. A check manifest with messages, exception eligibility, and supported native VI mappings.
7. Synthetic acceptance scenarios for that profile.

The same definitions can drive a small form or drop-down, the assistant's extraction schema, and the rules engine. This reduces differences between what the customer reviews and what the backend checks. UI styling is separate from semantics.

## Illustrative flight profile fragment

This JSON is documentation, not yet an executable profile. It shows the contract shape rather than a complete JSON Schema.

```json
{
  "profile_id": "travel.flight",
  "version": "1.0.0",
  "custom_constraint_type": "urn:intent-judge:flight-requirements",
  "fields": {
    "max_connections": {
      "value_type": "integer",
      "required_for_task": false,
      "minimum": 0,
      "question": "How many connections will you accept?",
      "choices": [0, 1, 2],
      "allow_explicit_no_preference": true,
      "operator": "lte",
      "offer_field": "flight.connection_count",
      "check_id": "FLIGHT_CONNECTIONS",
      "exception_allowed": true
    },
    "max_total_cents": {
      "value_type": "integer",
      "required_for_task": true,
      "minimum": 0,
      "question": "What is your maximum all-in price in USD?",
      "operator": "lte",
      "offer_field": "price.total_cents",
      "native_vi_type": "mandate.payment.amount_range",
      "check_id": "PRICE",
      "exception_allowed": true
    }
  },
  "approved_derivations": ["flight.connection_count.v1"],
  "offer_mapping_id": "demo.flight.checkout.v1"
}
```

Profile field names can differ from merchant field names through a reviewed mapping. They cannot differ from the approved semantics through an unreviewed model interpretation.

`exception_allowed` is only business eligibility. A price acceptance still requires native VI reauthorization when it exceeds the current signed maximum.

## Typed operators

Initial operators: `eq`, `in`, `lte`, `gte`, `between`, `contains_all`, and `required_true`. Their implementation defines supported types, boundaries, units, and missing-value behavior. They do not coerce arbitrary strings, compare boolean values as integers, or compare amounts across currencies.

`between` must specify endpoint inclusion and value type. Temporal predicates must define timezone and overnight semantics. Set membership must use canonical IDs or enums, not fuzzy model similarity. Text similarity and LLM judgment are not purchase-validation operators.

A derivation registry supplies named, reviewed functions such as connection count, trip duration, and hotel night count. Profiles reference those IDs. No `eval`, executable expressions, dynamic imports, model-generated Python, arbitrary URL fetches, or shell commands are permitted in profiles.

Schema validation ensures shape and types. Operator and derivation implementations establish meaning. A prompt alone cannot supply a trustworthy evaluator.

## Flight coverage

| Field | Clarification and normalized meaning | Signed offer facts needed |
|---|---|---|
| Origin/destination | Customer-reviewed airport set; broad regions need a reviewed mapping | First origin and final destination |
| Travel dates | One-way or round trip; actual dates, not an unresolved "next week" | Each required leg's dates |
| Departure window | Explicit airport-local window, including excluded hours | Departure time with offset and airport |
| Arrival deadline | Explicit local date and time at destination | Arrival date/time with offset |
| Connections | Maximum number of itinerary connections | Complete ordered legs/segments |
| Nonstop | No connections and no intermediate technical stops | Complete route and technical-stop information |
| Duration | Maximum elapsed trip time, if required | Ordered offset-aware times, including layovers |
| Cabin/fare | Explicit acceptable categories; basic economy is a distinct category | Fare/cabin for applicable segments |
| Baggage | Counts and types included in approved all-in price | Signed inclusion and allowance facts |
| Refundability | Specific refundable requirement, if chosen | Signed refundability/policy fields |
| Passengers | Approved count; synthetic data only | Signed passenger quantity |
| Price/currency | Total for approved passengers/trip, fees included, explicit boundary | Total, currency, and all-in scope |

Do not silently normalize "direct" to "nonstop"; ask the customer to confirm zero intermediate stops. Do not equate a single listed segment with proof of no technical stops unless the merchant schema explicitly guarantees complete route disclosure.

For the simple synthetic demo, fixtures disclose complete routes and technical-stop count explicitly. Derive connections as segment count minus one only after segment continuity and completeness checks. A two-leg itinerary with contradictory airports or impossible times is not a valid flight fact set.

If using the earlier `max_stops` field, define its meaning explicitly in that schema version and map it to the displayed label. The richer profile keeps connections and technical stops distinct. Preserve the standing custom constraint URN; version its internal schema rather than silently changing semantics.

"Under $300" is clarified into a visible boundary: strictly less than $300, or at most $300. The approved operator determines whether 30000 cents passes. USD amounts use integer cents; future currencies need explicit minor-unit handling.

## Hotel reuse example

A hotel profile replaces travel itinerary fields with destination/property, check-in/check-out dates, room and guest counts, total stay price, cancellation deadline, accessibility facts, breakfast, and relevant fees. The approval, exception, evidence, VI, and purchase-gate workflow stays the same.

"Near the venue" needs a confirmed maximum distance and a trusted location calculation. "Quiet hotel" lacks a reliable deterministic meaning until a supported, customer-reviewed criterion and data source are provided. Do not turn either phrase into a hidden guessed value.

Checkout time, refundability, refundable-until deadlines, resort fees, and nightly-versus-total pricing are separate facts. A hotel's advertised headline nightly rate cannot stand in for the signed all-in stay total.

## General mode

General mode accepts arbitrary language and identifies requested conditions. It can use shared fields, such as price and merchant, when a verified offer provides them. It visibly distinguishes supported, unresolved, and unsupported conditions.

General mode does not discard an unsupported requirement so that the remaining easy checks can pass. A request such as "buy an ethically sourced, comfortable chair" remains held for those conditions unless a profile supplies approved criteria and trustworthy corresponding facts.

New domains become enforceable by providing reviewed profile semantics and offer mappings. A second domain using only existing operators should require configuration and fixtures. A novel calculation or merchant API may require a small code extension.

## Adoption workflow

1. Integrator describes the domain and desired questions in natural language.
2. AI may draft a profile as a development aid.
3. A developer reviews its fields, meanings, operators, provenance, and scenarios.
4. The registry validates and pins the profile and merchant mapping.
5. Publish the supported capability manifest and test it with signed fixtures.
6. Customers use that reviewed version for drafts and approvals.

Runtime customer or merchant text cannot install or rewrite a profile. Semantically meaningful changes create a new version and invalidate earlier pending decisions. Adoption is designed to be low-code, not a promise that arbitrary conditions are executable without engineering.
