# Flexible conversation and typed intent

This document records the current design for the conversation layer after the
rigidity problems found in the first live flight walkthrough. It describes the
implemented boundaries and the remaining limits; it is not a claim of perfect
language understanding or a replacement for hosted user acceptance testing.

## Product rule

The conversation is a stateful interpretation step. It is not a form that asks
every field in a profile, and it is not a model deciding whether a purchase is
safe. A request is interpreted into a typed draft, the traveler reviews that
draft, and the deterministic rules engine checks the approved requirements
against merchant-signed offer facts. The model can extract, clarify, and explain;
it cannot approve a purchase.

The reviewed profile is the boundary for what can be enforced. A profile can be
reused for flights, hotels, or general commerce by changing its typed fields and
operators. Unsupported conditions remain visible and hold the workflow rather
than being silently dropped. A field that was not mentioned is not turned into a
question merely because the profile contains it.

## Stateful interpretation

Each interpretation carries the complete customer message history, the current
typed draft, the pending question contract, and a trusted server clock context.
The browser time zone is captured explicitly and validated as an IANA zone. A
relative phrase such as “within the next week” is normalized against the server
observed date and the chosen time zone; that clock context is never used as a
customer source quotation.

The model receives interface questions as read-only context. The question helps
it understand a short reply such as “MCO or MIA,” but interface copy can never be
used as evidence for a requirement. Source quotations must be contiguous text
from the customer. The deterministic reconciliation step then:

- preserves earlier fields, source quotations, clarifications, and unsupported
  conditions when a later provider response omits them;
- accepts a changed value only when its source quotation occurs in the latest
  customer turn;
- reopens a changed existing value for review instead of silently retaining the
  old value;
- treats an explicit optional no-preference answer as an unapproved choice that
  no longer needs to be asked again; and
- preserves independent requirements when one condition is ambiguous or
  unsupported.

Clarification planning is therefore source-backed and ranked. It asks for a
required missing value or a supported ambiguity the customer actually raised.
It does not interrogate every optional profile field. For example, a hard
`nonstop: true` requirement does not also trigger a contradictory maximum
connections question.

## Flight profile 1.2.0

Flight departure dates use the profile's `date_choice` operator. The approved
value can be:

| Shape | Meaning | Bound |
| --- | --- | --- |
| `"YYYY-MM-DD"` | One exact date | Canonical ISO date only |
| `{ "start": "…", "end": "…" }` | Inclusive travel window | Start must be on or before end; at most 366 days |
| `{ "dates": ["…", "…"] }` | Explicit discrete alternatives | 1–20 unique ISO dates |

The temporal normalizer handles explicit yearful dates, unambiguous numeric
dates, shared-year ranges, cross-year ranges, weekdays, and bounded relative
phrases. It leaves ambiguous, soft, negated, invalid, or overlong date phrases
for clarification. A date window is never collapsed to its first date merely to
make the model output fit an old single-date field.

This is still a bounded flight demo. Round-trip rules and arrival-time
requirements are outside the current profile and remain unsupported when a
traveler asks for them. The implementation must retain those words in the
review rather than imply that the profile enforces them.

## Airport identity and multiple choices

Airport identity context comes from the pinned offline `airportsdata==20260905`
package (7,884 IATA records, MIT licensed). Primary references are the
[PyPI project page](https://pypi.org/project/airportsdata/) and the
[upstream repository](https://github.com/mborsetti/airportsdata). The catalogue
is used for identity, spelling, search, and ambiguity detection only. It is not
flight inventory, availability, a merchant fact, or customer consent.

A city or region with multiple possible airports is kept ambiguous until the
traveler chooses. The UI can search by airport code, city, airport name, or
region and can add several airport chips. A customer can explicitly approve a
set such as “MCO or MIA”; the compiler retains both codes. It must not select
one airport because it is common, first in a list, or suggested by the model.
Regional suggestions such as Florida are chooser context, not an authorization
to use a particular airport.

The merchant-signed offer remains the only source for an itinerary's actual
origin, destination, date, connections, and price. The identity catalogue does
not make an offer match.

## UI decisions from the failure walkthrough

The old static date chip that inserted an unrelated November 12 value is not a
conversation answer. Date review now has three explicit modes: one exact date,
an inclusive range, or a finite list of dates. Unselected controls stay empty;
the interface does not manufacture a date to fill a required field. Airport
choices are multi-select and require an explicit use action, so selecting a
second airport does not send a hidden customer turn.

Long interpretation status text is rendered on its own live-status line outside
the 48px send control. The control keeps a stable icon-sized layout while the
status can wrap. Reduced-motion, keyboard focus, pending-state locking, and
error recovery are part of the same interaction boundary.

If a saved draft was created under an older profile revision, the application
keeps the entire conversation and captured summary read-only. The traveler must
explicitly choose “Update this saved conversation.” That action records the
profile refresh, reinterprets the preserved history through the current
two-stage pipeline, and opens a new review revision. It does not rewrite a
completed receipt or silently spend paid inference on page load.

## AI architecture and deterministic boundary

Live Foundry uses two audited stages: an extraction stage proposes a structured
intent envelope, and an independent coverage-audit stage checks field coverage,
source grounding, unsupported conditions, and clarification reasons. The
deterministic compiler then normalizes dates, airport identity, boolean scope,
and state changes. This compiler is a safety boundary, not a scripted substitute
for the model: it repairs bounded representation errors and rejects unsupported
or ungrounded values. It does not invent missing customer requirements.

The final purchase decision still comes only from the deterministic rules engine
over the customer-approved requirements and verified merchant-signed offer. A
missing merchant fact is `HOLD`. Synthetic demo offers are fixed at $295 and
$280; a request with an under-$200 approved budget correctly holds both offers.

## Recorded experiment boundary

`evals/experiments/stateful-flexibility-20261014.json` retains six actual model
rows: three conversation cases evaluated with low and medium reasoning. The
original raw results passed 1/6. After the grounding/compiler fixes, the file
also stores a `compiler_replay` for each row. Those replays were run without new
inference and retain the original scores; they show what the updated compiler
would produce for the saved responses, including date windows and explicit
airport alternatives. They are not fresh model-accuracy results.

The low-versus-medium comparison is three cases per setting and is not a
statistical ranking. The ledger moved from 198 to 210 reserved stages and from
$18.84 to $19.08 during that bounded experiment. That reservation history is
additive and must not be reset or interpreted as the remaining Azure student
credit. Final hosted deployment, fresh blind UI walkthroughs, and the remaining
UAT checks are recorded separately when completed; this document does not mark
them complete.

## Verification and failure truth at the release checkpoint

The current source checkpoint is `07b5c618ae0ab33c4f17b486030ddc34f5e27d35`.
Its Vercel production deployment is READY as
`dpl_DcXbAqVG1BeebBisE4Thh8GgNpSN`, with the main alias
`https://intent-judge-perfected.vercel.app`. Local verification at this
checkpoint reports 315 tests passing with one upstream warning. A separate
fresh-local browser pass reports eight checks passing. CI run
`38498845176` subsequently completed successfully with the same 315-test and
eight-browser-check result. A final deployment/native-original checkpoint is
still separate and is not claimed here.

The earlier public `5e` release had eight actual public-browser checks and a
native walkthrough of the exact Florida request. That walkthrough used four
audited sends (eight model stages) and retained the approved `$199.99` limit,
EWR origin, the explicitly chosen MCO-or-MIA destination set, the inclusive
October 14–21 window, and nonstop. No unsupported condition or repeated
clarification remained. The two fixed synthetic offers at $295 and $280 both
correctly held on the budget check, and the purchase gate refused them. A first
native Florida variant still left the raw marker `flight to Florida`; the later
`5e` change removed only the bare geographic marker after actual Florida
airports were selected. Unrelated baggage and LAX-mismatch cases continued to
hold and were not counted as solved by that narrow geo fix.

The independent global CPH-to-ICN request exposed a separate real failure on
that release (reference `c213b8782aee`). The paid two-stage reproduction is
archived in `evals/experiments/global-flight-clock-20261014.json`. The extractor
returned `120000` cents for “under 1,200,” which is the wrong strict price
interpretation. The coverage auditor classified the price as a clarification,
and the grounding layer rejected the exact `08–20` time window because the
customer wrote dotted meridiems such as `8 a.m.` and `8 p.m.`. Both model stages
also omitted “one adult” and “May 7 preferred.” The bounded source-coverage
guard preserves those phrases as unsupported because the current flight profile
cannot enforce passenger quantity or date priority; the hard May 5–9 window is
retained.

The temporal parser fix now accepts dotted and colon meridiem forms without
inventing minutes or turning `8 p.m.` into `08:00`. The archived failure and any
compiler replay remain historical evidence; they are not new inference and do
not establish that the final native global repeat has passed. That repeat was
still pending at this checkpoint.

The choice-flow fixes retain selected airports and never auto-send a customer
turn. Airport selections remain disabled while interpretation is pending rather
than disappearing. Empty airport and date `Use` controls remain disabled until
their values are ready, airport names render with an explicit “or,” and an
interpretation failure does not force the user into offline mode. These are
interaction fixes; they do not convert a provider failure into a successful AI
interpretation.

## Follow-up verification and bounded recovery

The original native global repeat on source `07b` still failed, reference
`ea199b6e65db`. Both actual model stages emitted `120000` cents for “under
$1,200,” although the strict integer-cents value is `119999`. The retained
failure and its `compiler_pipeline_replay` are in
`evals/experiments/global-flight-followup-20261014.json`; the replay used no
new inference and does not change the original model result. A new final
deployment/native-original run was still pending at this checkpoint and must
not be described as accepted.

The audited recovery is deliberately bounded. When a candidate contains a
`GroundingFailure`, actual quote-grounded fields that are independently safe
are preserved, while the bad value is quarantined. The exact money quote is
compiled deterministically to `119999`; other ambiguities remain
clarifications. Unknown customer scope remains preserved instead of being
truncated. Malformed envelopes, all-unsafe candidates, and provider errors
still return a typed failure. This recovery improves salvage of a partially
valid response without allowing the model to approve or invent a requirement.

A separate fully supported CPH-to-ICN request on source `07b`, without the
unsupported “one adult” or “May 7 preferred” clauses, passed one audited send.
It recorded only explicit no-preference choices that were actually specified;
the fixed $295 offer passed, the $280 offer held, and the purchase had zero
exceptions. The receipt was `C0tDj0mquiQsJq3876IMig`, intent
`km6P1yIlwOhENx5P2jmCsA`, and the 34.1 KB evidence JSON was downloaded and
reloaded. The evidence was checked for the canonical digest, trusted issuer
and merchant signatures, exact offer hash, approved-requirements digest,
native VI evidence, and the final analyst recommendation. This is a bounded
successful path, not evidence that the failed original global request is fixed
in every form.

The durable ledger stood at 236 reserved stages and 1,960 reserved cents
($19.60) at this checkpoint. That is additive application accounting, not a
claim about remaining Azure student credit. Seven legacy demo aliases retain
direct city normalization for compatibility; other catalog cities remain
ambiguous until the customer chooses an airport.

