# Evaluated conversation and continuous quality

This revision responds to Victor's feedback that the prototype felt like a prompt followed by a form. The new entry point is a conversation, with a live summary and profile-driven follow-ups. Victor confirmed this direction. The final authorization remains a separate explicit review.

## What runs

`app/ai_pipeline.py` uses the existing Azure Foundry gpt-oss-120b deployment. The selected **audited** pipeline performs two actual provider calls: extraction, then an independent coverage audit against the original customer conversation. Both envelopes pass strict field-type and exact-source-quotation validation. The audit can correct supported values, but cannot discard the first stage's unsupported conditions. It has no purchase authority. Trace records contain the actual stage, deployment, duration, tokens and provider response ID.

`app/conversation.py` ranks missing required profile fields before optional preferences. `/api/intents/{id}/clarify` interprets the accumulated customer messages, stores provenance, and checks the revision before inference and again in the conditional write. A new turn removes the current approval and offer views. Earlier decisions then fail the purchase freshness gate. Each reply is bound to the profile question displayed at that moment. Structured interface questions are passed as context, while source validation accepts quotations only from actual customer messages. Immutable interpretation snapshots preserve fields, sources, flags, guidance, conversation digests and source-message indexes per revision, and are included in signed evidence. Two follow-up turns are allowed, after which the customer can edit every field in review.

The AI never declares no preference. The final review explicitly records every field or no preference. If a model flags an ambiguity as unsupported, the traveler can specifically remove that flag as a separate requirement in review; this records its exact text, original revision/digest and timestamp in the event chain. The AI cannot remove it during clarification. The original conversation and removal remain in the signed evidence.

## Experiments and selection

The corpus contains 24 synthetic gold cases: 12 development, 6 untouched holdout, and 6 regression cases for future rotation. Gold scoring checks exact normalized fields, unexpected fields, quoted source coverage, required unsupported conditions and unnecessary holds. It does not ask a model to grade itself.

| Pipeline | Split | All checks passed | Median wall time |
|---|---|---|---|
| Original extractor | Development | 10/12 | 1,424 ms |
| Guided extractor | Development | 10/12 | 1,322 ms |
| Extraction + independent audit | Development | 11/12 | 2,867 ms |
| Selected audited pipeline | Untouched holdout | 6/6 | 2,942 ms |

The original extractor failed validation on a time-window case and added a bypass instruction as an unsupported condition. Guided extraction dropped a return requirement and failed one direct-flight response. Auditing preserved the return requirement and improved development performance, but still missed the direct-flight ambiguity. The holdout included corrections, negations, an inclusive price boundary, an overnight window, hotel proximity and multiple flight requirements. These are small synthetic samples, not a reliability guarantee.

The 60 evaluation calls stayed inside their configured allowance. Reports in `evals/reports/` preserve outputs and failures. Failed responses did not produce drafts; therefore report trace totals count **recorded validated stages**, rather than every charged attempt. The shared server ledger records all reservations and returned usage. No new paid model deployment was created: this isolates the effect of the pipeline and protects the student's remaining credit. West US 2 did not offer the expected OpenAI mini model SKU in this account during inspection.

A subsequent browser test exposed a failed validated follow-up and over-classification of missing airports. It remained visibly failed with no fallback. A fresh live run completed clarification, approval, PASS/HOLD comparison, actual 409 refusal, exact exception, simulated receipt, signed evidence and reload. This evidence motivates specific customer resolution of flags rather than trusting the AI to erase them.

## Continuous testing

`.github/workflows/tests.yml` runs the provider-independent regression suite and JavaScript syntax checks on every push and pull request. It needs no Azure credentials and runs with `MOCK_LLM=1`; provider tests explicitly inject synthetic responses.

Vercel production cron requests `/api/internal/quality-check` daily at **07:00 UTC**. A bearer `CRON_SECRET` is mandatory and compared safely. An atomic date-specific claim permits at most one rotating case per day; retries return the stored report. The live canary uses the selected pipeline and `purpose=monitor`, with at most two calls/day and 40 calls over its lifetime. A failure reports `failed` or `unavailable`; it never passes a mock response, switches models, changes production prompts or overrides a purchasing gate. A claimed run is immediately visible. If the worker is interrupted, a running record older than 75 seconds becomes `unavailable` on read or replay; paid inference is not retried that day.

The public `/api/quality` and Quality view expose only synthetic benchmark aggregates and the latest canary result. No customer conversation or credentials appear. The first real canary passed the no-stop-preference case with two model stages, and a repeated authenticated request returned identical stored output without new inference.

All inference purposes share the existing **200 reservations × $0.10 = $20 lifetime allowance**, without resetting earlier usage. Interactive use stays at 8 calls/session and 40/day; experiments have a separate 60/day ceiling; monitor use has its smaller ceiling. These are conservative application limits, not an Azure subscription spending lock. Unrelated Azure services or manually invoked external tools remain outside this ledger. No emergency budget increase was made.

## Reproduction

```sh
MOCK_LLM=1 .venv/bin/pytest -q
PYTHONPATH=. .venv/bin/python scripts/benchmark_ai.py --variant audited --split development
playwright-cli -s=intent-v2 run-code --filename=scripts/browser_conversation.js
```

The benchmark command is explicitly paid and may be refused by the existing daily/lifetime cap. It never resets the ledger. For UI testing, first open the desired local or hosted URL in that named Playwright session. The browser script deliberately performs customer review/removal actions and a simulated purchase; it is not an AI approval test.

The design uses the installed design-style-guide, image-to-code references, a Linear-informed Swiss product density, Web Interface Guidelines review and rendered Playwright checks. References guide layout only; generated airline logos, baggage defaults, identities and passenger counts were not implemented.

Sources for the approach: [Microsoft agent evaluation concepts](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/agent-evaluators), [Microsoft structured outputs](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs), [Vercel cron limits](https://vercel.com/docs/cron-jobs/usage-and-pricing), [Vercel cron authentication](https://vercel.com/docs/cron-jobs/manage-cron-jobs). The gold scorer is our application code; we do not claim integration with a managed Foundry evaluation service.
