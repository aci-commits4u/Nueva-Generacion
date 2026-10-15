# Environments and release workflow

The public product and ongoing development use separate release targets. The
current accepted snapshot is `d6f8131` from `victor/perfected`; that snapshot
is now the starting point for both `production` and `develop`.

| Target | Working tree | Git branch | Vercel project / URL | Runtime | Purpose |
|---|---|---|---|---|
| Development | `/Users/victor/Nueva-Generacion-dev` | `develop` | `intent-judge-perfected-dev` / [intent-judge-perfected-dev.vercel.app](https://intent-judge-perfected-dev.vercel.app) | `APP_ENV=development` | Deployed work-in-progress and exploratory UAT |
| Production | `/Users/victor/Nueva-Generacion` for release operations | `production` | `intent-judge-perfected` / [intent-judge-perfected.vercel.app](https://intent-judge-perfected.vercel.app) | `APP_ENV=production` | Public demo and reviewed releases |

Both projects are in team `team_HBbhk99lljqf4KKzGX8d84Yk`. The production
project ID is `prj_sQQGLWLVZ7qigP9WePx9fIH5kzWT`; the development project ID is
`prj_BQgv2BqYWbrJjqW0LkPw13cVC8jc`. `victor/perfected` remains the historical
implementation branch; new feature work starts from `develop` and reaches the
public alias only after an explicit promotion to `production`.

The production project and public alias stay unchanged while development work
is prepared. Development sessions use `AZURE_TABLE_NAME=IntentJudgeDev` and
production sessions use `AZURE_TABLE_NAME=IntentJudge`. Each project receives
its own `DEMO_SIGNING_KEYS`, so a development signature cannot impersonate a
production signer. The global AI money and call reservation ledger is shared by
setting development `AI_BUDGET_TABLE_NAME=IntentJudge`; production uses its
existing default ledger. This isolates user sessions and signing identities
while keeping the budget truthful across environments.

The two projects receive separate environment-variable configuration. The
development project must never inherit a production `.env` file by copying it
into Git or browser artifacts. Development has no `CRON_SECRET` requirement
because the guard removes the production quality cron from its upload;
production retains the cron and requires `CRON_SECRET`.

## The guard

`scripts/prepare_deployment.py` prepares a JSON manifest for the manual Vercel
MCP upload. It does not call Vercel, create a deployment, read secret values,
or modify Git. Its default target is development:

```sh
python scripts/prepare_deployment.py --output /tmp/intent-judge-dev-manifest.json
```

The guard requires all of the following before it emits a manifest:

- the working tree has no tracked or untracked changes;
- the current branch is `develop` for development or `production` for a production release;
- `origin/<branch>` points at the exact `HEAD` commit;
- the latest GitHub Actions run for that commit is complete and green;
- both `deterministic-regression` and `Browser UI regression` completed successfully;
- the selected Vercel project is the fixed project in the script, rather than a caller-supplied project ID;
- the upload set contains only tracked files under `app/`, `web/`, `profiles/`, `demo/`, `evals/`, plus `requirements.txt` and `vercel.json`.
- development includes `AI_BUDGET_TABLE_NAME` and production includes `CRON_SECRET` in the required environment-key manifest; the manifest never contains their values.

The manifest contains SHA-1 digests and byte sizes so the MCP upload can prove
that it sent the reviewed source. It contains no file contents except a small
development-only `vercel.json` override. That override removes the production
quality cron from the development upload so development cannot spend model
budget through the production scheduler. Production keeps the repository
`vercel.json` unchanged.

The Vercel API target is `production` for both projects because each project
has its own stable deployment alias. The runtime environment is still explicit
in the manifest: development uses `APP_ENV=development`, while production
requires `--environment production` and uses `APP_ENV=production`.

## Release sequence

1. Create a feature branch from `develop`.
2. Make and review the change locally.
3. Merge the reviewed feature into `develop`.
4. Run the guard on `develop`, upload the emitted manifest to the development
   project, and complete deployed browser/UAT checks.
5. Promote the exact reviewed commit into `production`.
6. Run the guard again with the explicit production environment:

   ```sh
   python scripts/prepare_deployment.py \
     --target production \
     --environment production \
     --output /tmp/intent-judge-production-manifest.json
   ```

7. Upload that production manifest through the existing manual MCP deployment
   path. This is the final release action; ordinary feature pushes cannot
   affect the public project.

There is intentionally no automatic production deploy in GitHub Actions. The
existing workflow is a test gate only, and no Vercel token is stored in GitHub.
The repository account has write access but does not have administrator access,
so branch protection and required-reviewer environments cannot currently be
enforced through GitHub settings. Until that access exists, the clean-tree,
exact-commit, green-CI checks plus deliberate production promotion are the
release control.

## Shopping boundary

Flights have an additional read-only live discovery path through Kiwi's MCP
server. After the traveler approves flight requirements, the UI can request
current external quotes and expose a validated outbound booking link to Kiwi.
Those records are explicitly external and unsigned: they are advisory
observations, cannot authorize or execute a purchase, and cannot replace the
merchant-signed checkout used by the Verifiable Intent demo.

Hotels and General currently have no live shopping provider. They use the same
AI clarification, typed approval, signed synthetic offer, deterministic check,
and evidence workflow. The signed demo flow remains synthetic across every
domain, even when live flight discovery is shown beside it.

## Non-negotiable product rules

The model never approves a purchase. The approved typed requirements are the
source of truth, and every checkout fact comes from a verified merchant-signed
`checkout_jwt`. Missing data is a `HOLD`; `/api/purchase` rejects with HTTP 409
unless the offer passes or every difference has a specific exception bound to
the exact offer hash. The UI says “intent-checked” and does not claim
Mastercard certification or liability protection. Foundry failures remain
visible and do not silently retry or switch to an offline parser. Secrets,
signing keys, and browser state stay out of source and artifacts; automated UI
verification is headless-only on the shared Mac.

The application still uses synthetic commerce, signed demo offers, and the
existing hosted environment secrets. The guard never changes the AI budget,
resets the ledger, enables a fallback, or claims that a deployment is safe just
because CI passed; deployed user-flow testing remains a required release step.
