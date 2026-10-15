## Deployment workflow

- Treat `production` as the public release branch and `develop` as the isolated development branch.
- Branch feature work from `develop`; run deterministic and browser regression checks before merging.
- Run `scripts/prepare_deployment.py` before any manual Vercel MCP upload. Its default target is `develop` and it refuses dirty trees, stale remote branches, missing CI, wrong release branches, and arbitrary project IDs.
- Production requires `--target production --environment production` and a reviewed commit on `production`.
- Keep the development and production Vercel projects, Azure storage names or partitions, runtime environment values, and deployment aliases separate. Never commit or print `.env` values.
- GitHub Actions is currently a test gate only. Do not describe this repository as having automatic Vercel deployment or branch protection until those controls are actually configured.

## Product safety boundaries

- The AI drafts, clarifies, and explains; it never approves a purchase. Only the deterministic rules engine can produce `PASS`, `HOLD`, or `BLOCK`.
- The customer-approved typed requirements are authoritative. Do not make a checkout decision from a prompt summary, free text, or model explanation.
- Purchase facts must come from the verified merchant-signed `checkout_jwt`. Missing or invalid merchant facts produce `HOLD`.
- `/api/purchase` must return HTTP 409 unless the decision passes or every eligible difference has a specific recorded exception tied to the exact offer hash.
- The product label is “intent-checked.” Do not claim Mastercard certification, liability protection, or a final liability decision; the evidence packet ends with a dispute analyst recommendation.
- Kiwi live flight discovery is read-only and external. Its unsigned quotes and outbound Kiwi links stay separate from the synthetic signed Verifiable Intent demo flow and can never authorize, purchase, or replace signed-offer enforcement.
- Hotels and General currently use the shared intent layer with synthetic signed demo offers; they do not have live shopping integrations.
- Foundry failures are visible. Do not silently retry, switch to offline parsing, or fabricate a draft after a provider failure.
- Use synthetic data only and keep credentials, signing keys, connection strings, and browser state out of source, logs, and artifacts. Automated UI verification is headless-only on the shared Mac.
