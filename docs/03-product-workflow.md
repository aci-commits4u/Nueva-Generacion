# Product workflow and approval contract

Status: proposed behavior, based on Victor's requirements and the project's standing safeguards.

## 1. Capture and clarify

The customer chooses a domain or confirms a suggested domain. An AI assistant reads the conversation and the trusted profile, drafts typed requirements, and proposes relevant questions. Switching domains invalidates the draft and requires a new review.

Every supported field has an explicit state:

| State | Meaning | May become authorization? |
|---|---|---|
| `specified` | The customer supplied or confirmed a value | Yes, after explicit approval |
| `no_preference` | The customer explicitly chose not to restrict this field | Yes, recorded as deliberate absence of a restriction |
| `unresolved` | Missing, ambiguous, contradictory, or merely proposed by AI | No |
| `unsupported` | The system cannot evaluate the requested condition | No; route to supported profile or manual review |

Null is not consent. The assistant cannot select `no_preference` for the customer. Required transaction identifiers and structural fields, such as destination and travel date, cannot be dismissed when the profile needs them to define a purchase.

Keep a coverage ledger containing requirement candidates, source message IDs and exact spans, their mapped field, proposed normalization, and unresolved issues. Validate cited spans against stored messages. LLM confidence is descriptive metadata only.

For a field absent from the original request, a trusted profile supplies question wording. Profile-driven questions improve coverage, but no checklist proves that every possible human requirement was captured.

## 2. Review and authorize

Show the original request alongside a deterministic rendering of every proposed requirement and explicit no-preference choice. Show changes across clarification turns. The customer can edit values and correct omissions.

The approval action binds the exact requirement set ID, revision, canonical digest, profile ID/version/digest, conversation revision, and approval timestamp to the authenticated customer session. A boolean supplied in a request body is not evidence that approval happened.

Once issued, the approved object is immutable. Changing a value, profile semantics, or an approval-relevant conversation answer requires a new version and new approval. The backend constructs the authorization from its stored version rather than accepting a client replacement object.

For flights, `ApprovedRequirements` remains carried in the VI custom constraint `urn:intent-judge:flight-requirements`. The original conversation and `prompt_summary` cannot independently cause a purchasing PASS.

## 3. Obtain and check an offer

An external shopping system or the separate demo adapter submits an offer. The backend verifies the VI chain, signed checkout, identity and binding, then normalizes signed facts under the pinned profile.

The deterministic rules engine evaluates the native-verification findings and every applicable domain rule. Each business check returns:

```json
{
  "check_id": "FLIGHT_CONNECTIONS",
  "requirement": {"operator": "lte", "value": 0},
  "offer_value": 3,
  "status": "fail",
  "message": "You approved zero connections. This offer has three."
}
```

Check statuses are `pass`, `fail`, or `missing`. Explicitly unrequired fields are excluded from the applicable check list and remain visible in the approval record.

| Decision | Conditions |
|---|---|
| PASS | Required approval and verification gates pass; every applicable business check passes |
| HOLD | Business mismatch, missing required offer data, unresolved approval, unsupported capability, or required verification still incomplete |
| BLOCK | Invalid signature, credential tampering, identity/hash mismatch, or another definite integrity failure |

Missing data never counts as a pass. A structurally invalid offer cannot be rescued by interpreting its untrusted description with an LLM.

## 4. Review specific exceptions

For an otherwise valid offer, the customer may accept a supported business mismatch or knowingly accept a missing domain fact. The screen must describe the exact issue and accepted value or uncertainty.

Examples: "Accept three connections instead of zero on this offer" and "Buy this offer despite the merchant not stating whether it is refundable." The second example records unknown refundability; it must never record the offer as refundable.

An acceptance records the authenticated actor, decision ID, check ID, original approved requirement, actual accepted value or missing-field state, offer hash, requirement revision/digest, profile digest, and timestamp. A signed authorization record must bind these facts before they become authority. Preserve the original failed check.

Approval, cryptographic integrity, offer identity, expired authorization, unsupported evaluators, and required verification capability are not waivable business checks.

If a native VI constraint changes, such as a price limit or product allowlist, obtain a new user-signed mandate or suitable exact-cart authorization, then verify again. A database exception never makes a violating old mandate valid. See [VI integration](06-verifiable-intent-integration.md).

## 5. Enforce at execution

`POST /api/purchase` refuses with HTTP 409 unless the decision is PASS or every applicable failed/missing business check has a valid, offer-specific acceptance and all required approval/integrity/native-verification gates pass.

The server reloads authoritative records and rechecks offer freshness, signature, amount, currency, requirement version, profile version, exceptions, and replay state immediately before execution. It must execute the exact checked checkout. A different checkout requires another evaluation and confirmation.

A HOLD with complete accepted exceptions remains historically a HOLD with exceptions. The record distinguishes it from a purchase that matched the original requirements.

The endpoint returns a simulated receipt when using demo commerce. Live booking/payment integrations are separate work.

## 6. Explain and preserve

AI may explain supplied check results or summarize evidence. It cannot change the decision, soften a failed check into approval, choose an exception, or assign liability. Deterministic messages remain available if the model fails.

Evidence includes both what was approved and what deviated. Its terminal field is `"final_decision": "dispute analyst"`. Absence of a captured requirement is a possible extraction or consent gap, not automatic proof that the customer is responsible.
