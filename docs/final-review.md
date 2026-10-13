# Release review

A separate, fresh-context reviewer inspected the complete implementation and deployment configuration. No Critical findings were reported. Four Important findings were reproduced and fixed in one regression pass:

| Finding | Correction | Evidence |
|---|---|---|
| Explanation buttons sent GET to a POST endpoint | Send an explicit POST body | Browser reproduced GET 405, then POST 200 |
| Extra signed payment-reference constraint received unchecked PASS | Validate role, unique instance and exact disclosure reference | `test_extra_checkout_reference_cannot_receive_unchecked_pass` failed then passed |
| Allowed session growth exceeded Azure's 1 MiB entity limit | Compress the complete atomic session into bounded binary properties; migrate old records on write | `test_full_decision_allowance_and_receipt_fit_hosted_entity`; actual Azure HTTP flow with 25 checks, receipt, retry and recovery |
| Emergency parser dropped unrecognized conditions | Preserve all text beyond consumed spans and a small neutral grammar; additional review textbox can record missed requirements | Five distinct unsupported additions failed then passed; rendered review recorded wheelchair assistance and backend held both offers |

The duration rounding finding was regraded Important: a traveler could receive an itinerary exceeding the approved maximum. Duration now rounds up; `test_fractional_duration_is_never_rounded_down` failed then passed.

The resulting local suite has 50 passing tests. Browser regression checks use the real application and Azure state. Provider calls are reserved for explicitly identified live evaluations, not repeated unit tests.

Azure's entity/property limits are documented in [Microsoft's Table service data model](https://learn.microsoft.com/en-us/rest/api/storageservices/understanding-the-table-service-data-model). Compressed binary property chunks are at most 60,000 bytes; combined compressed data is limited to 900,000 bytes, leaving metadata headroom. Conditional writes retain atomic purchase/idempotency state.

## Rulings and remaining limits

| Reviewed behavior | Decision and reason | Cost if that assessment is wrong |
|---|---|---|
| Cross-session records | Keep session-confined lookups and HTTP-only cookie | Disclosure or unauthorized use of another demo session |
| Stale approval and replayed exceptions | Keep current approval equality and exact signed bindings | Unapproved simulated booking |
| Exception expiry | Offer and VI expiry are rechecked; separate exception expiry is unnecessary for this demo | Consent might outlive an intended shorter period |
| Returning an existing receipt | Keep idempotent retrieval; it creates no new purchase | Confusing old receipt after a changed approval |
| Concurrent purchase | Keep SQLite transactions/Azure ETag retries; no external payment side effect | Duplicate simulated record if transactional storage fails |
| Local ephemeral signing keys | Keep local convenience; hosting requires stable environment keys | Local restart invalidates old local demonstrations |
| Missing business facts | HOLD; eligible specific unknown facts can be explicitly accepted | Traveler accepts unavailable information |
| Merchant totals, identity, currency and checkout hashes | Independent signatures and bindings reject tampering | Incorrect simulated checkout if verifier has an undiscovered flaw |
| Unknown constraints | Keep unimplemented constraints held; reference instance loophole is now fixed | Unsupported semantics falsely accepted if a future evaluator is incorrect |
| AI extraction and injection | Keep reviewed drafts and non-authoritative explanations; no perfect-interpretation claim | A traveler may still miss an incorrectly extracted requirement |
| Resetting anonymous sessions | Keep reset; durable global/day AI quota still applies | More storage use or earlier global allowance exhaustion |
| Failed AI requests consume reservations | Keep conservative accounting | Allowance ends sooner than necessary |
| Anonymous session/storage abuse | Accept bounded student-demo availability risk; no real payment | Storage costs or service availability loss |
| No wallet authentication or real commerce | Keep explicit synthetic scope | Not usable as production payment infrastructure |
| Evidence includes original HOLD after price reauthorization | Keep provenance and amended bundle/consent | Analyst must inspect both stages rather than a single final snapshot |
| Accepted-state UI after reload | Consent remains stored; user may review it again | Extra review click; backend remains authoritative |
| Reset retains server records | Keep evidence while opening a fresh workspace | Retained synthetic records need eventual cleanup |
| Malformed Content-Length | Treat as an availability/error-handling follow-up | Malformed clients may receive an error response |
| Broader domain features | Keep unsupported conditions held and document profile boundaries | Broader use requires new reviewed operators/fact adapters |
| Test-client warning and dependency ranges | Keep working versions; pinned VI commit | Future upstream updates may require compatibility maintenance |
| Foundry JSON-format incompatibility | Plain JSON instructions and strict parsing on the existing deployment | Provider behavior changes may surface visible extraction errors |
| Durable hosting choice | Azure Table instead of inaccessible marketplace integration | Storage latency and Azure credential maintenance |
| Budget reservation | Conservative $0.10/call, $20 lifetime ordinary allowance; no automatic emergency increase | Reservation does not replace Azure billing or cover unrelated subscription activity |
| Branch and release | Preserve `victor/perfected`, publish the separate Vercel project under existing authorization | Future iteration must explicitly choose how to integrate with the team's main branch |

No unresolved authorization finding was deferred. The scope and operational limitations above remain explicit prototype boundaries.
