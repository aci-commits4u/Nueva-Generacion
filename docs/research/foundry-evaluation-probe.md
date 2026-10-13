# Microsoft Foundry evaluation probe

This probe publishes the stored reliability-development outcomes to the native
Microsoft Foundry Evaluations API. It evaluates existing responses against the
saved gold labels; it does not generate new responses or call a judge model.

## Source and contract

The publisher selected the newest file matching `evals/reports/reliability*.json`:

`evals/reports/reliability-audited-revised-2026-10-13.json`

That report is labeled `typed-clarifications-v2` and contains seven stored rows,
including six revised passes and one revised failure. Each row retains its
`original_case` and `original_score`, which recorded the earlier 5/7 labeling.
Each uploaded item contains:

- `case_id` and the original request in `query`;
- the actual stored response in `response`, limited to `fields`, `sources`,
  `unsupported`, `clarifications`, and `error`;
- the typed gold contract in `reference`, including expected fields,
  unsupported-condition groups, clarification groups, allowed extras, and the
  hold policy.

The custom code grader is named `canonical_intent_gold`. It implements the
application's deterministic gold comparison: typed field equality (with the
same order-insensitive handling for string lists), rejection of unexpected
fields, exact source-quote presence in the original request, and coverage of
the expected unsupported-condition groups. It independently requires every
structured clarification to contain a non-empty `field`, `source_quote`, and
`reason`, and requires each clarification source quote to occur in the
original request. Clarification groups are checked separately from unsupported
groups. A stored error is a failed item.
The grader returns only `1.0` for a complete pass or `0.0` otherwise. Its
local contract check on the clarification-aware report produced
`[1, 1, 1, 1, 1, 1, 0]`, matching the revised six-pass/one-failure split.

## Native API configuration

The publisher used the project endpoint supplied by the native Foundry UI:

`https://victor-lead-foundry-20261012.services.ai.azure.com/api/projects/lead-team`

With the OpenAI-compatible evaluation routes, the exact calls were:

1. `GET /api/projects/lead-team/openai/v1/evals?limit=100` to verify that the
   name was not already present.
2. `POST /api/projects/lead-team/openai/v1/evals` with evaluation name
   `historical reliability-development-v1`, a `custom` data source config, and
   one `python` testing criterion named `canonical_intent_gold`.
3. `GET /api/projects/lead-team/openai/v1/evals/{eval_id}` to read the created
   evaluation back.
4. `POST /api/projects/lead-team/openai/v1/evals/{eval_id}` to update the
   existing criterion with the clarification-aware Python grader. The earlier
   native run remains retained under the same evaluation.
5. `POST /api/projects/lead-team/openai/v1/evals/{eval_id}/runs` with one
   `jsonl` `file_content` source containing the seven inline `item` objects.
   The request contains no target, model, completions, responses sampling, or
   generation configuration.
6. `GET /api/projects/lead-team/openai/v1/evals/{eval_id}/runs/{run_id}` until
   the run reached a terminal status.

Authentication used the existing Azure CLI session through
`az account get-access-token --resource https://ai.azure.com`. No token or
secret was written to this document or printed by the publisher.

The implementation is [scripts/publish_foundry_evaluation.py](../../scripts/publish_foundry_evaluation.py).
It defaults to a dry-run; `--execute` performs one create-or-reuse/update and
one run. The dependency-free `--self-test` exercises a valid clarification,
an unquoted clarification, and a missing unsupported group without contacting
Foundry.

## Readback result

The native evaluation was created successfully for the first publication, then
updated through the documented evaluation update route for the clarification
aware grader. The original native run remains available:

- Evaluation ID: `eval_ff8c6a76362a4ad58f40a38a6e361852`
- Evaluation name: `historical reliability-development-v1`
- Testing criterion: `canonical_intent_gold`
- Original run ID: `evalrun_0cfc9bd1583544b097433dc775776a42`
- Original run counts: 7 total, 4 passed, 3 failed, 0 errored, 0 skipped
- Original portal report: [open the original native evaluation run](https://ai.azure.com/nextgen/r/xagNntfoRYS1VFrLbdrcsg,lead-team-rg,,victor-lead-foundry-20261012,lead-team/build/evaluations/eval_ff8c6a76362a4ad58f40a38a6e361852/run/evalrun_0cfc9bd1583544b097433dc775776a42)
- Additional run ID: `evalrun_76250acff5c04b759d6fb687f3a43e94`
- Additional run status: `completed`
- Additional native result counts: 7 total, 6 passed, 1 failed, 0 errored, 0 skipped
- Additional native per-criterion counts: `canonical_intent_gold` — 6 passed, 1 failed,
  0 errored, 0 skipped
- Additional native run model field: `null`
- Additional portal report: [open the clarification-aware native evaluation run](https://ai.azure.com/nextgen/r/xagNntfoRYS1VFrLbdrcsg,lead-team-rg,,victor-lead-foundry-20261012,lead-team/build/evaluations/eval_ff8c6a76362a4ad58f40a38a6e361852/run/evalrun_76250acff5c04b759d6fb687f3a43e94)

The additional native result counts equal the revised stored report counts,
while the contradictory-shopping failure remains failed. The original 4/7
native run remains retained for comparison. These are native Foundry
evaluation runs backed by saved response data; they do not claim that a new
model was invoked during publication. A final readback of the project listed
one evaluation with this name and two completed runs with these result counts.

## Official references

- [Introduction to cloud evaluation with the Microsoft Foundry SDK](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/cloud-evaluation)
- [Create an evaluation](https://ai.azure.com/api-reference/evals/create-eval/)
- [Update an evaluation](https://ai.azure.com/api-reference/evals/update-eval/)
- [Create an evaluation run](https://ai.azure.com/api-reference/evals/create-eval-run/)
- [Custom evaluators](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/custom-evaluators)
