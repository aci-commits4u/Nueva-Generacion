# Intent Judge — start here for the Devin handoff

Victor wants one Devin session per feature, in parallel with exclusive file ownership. Do not run the entire project as one implementation chat. This is a hackathon: submission is October 12, 2026 at 2:30 PM America/New_York, feature freeze target 2:00 PM. Favor a complete two-minute demo and a defensible five-minute pitch. Keep Victor informed of findings and meaningful decisions. Do not restart a long discovery/planning process or change agreed authority rules.

Read `docs/handoff/README.md` for the exact state, research, interfaces, known gaps, and session plan. Then start separate sessions using:

1. `docs/handoff/sessions/01-ai-conversation.md`
2. `docs/handoff/sessions/02-rules-consent.md`
3. `docs/handoff/sessions/03-vendor-evidence.md`
4. `docs/handoff/sessions/04-api-integration.md`

Each session reads `AGENTS.md`, this handoff, its relevant project docs, and its task brief. It owns only its assigned files. It works on its own branch/worktree from the supplied `victor/rules` snapshot. It does not revert other work or merge/push shared main. The integration session owns assembly; Josue owns frontend/user flow. Verify the state of his current work before editing any of his files.

The product is a confirmation and evidence layer for agent-driven commerce. Flights are the implemented demo domain; other categories are a planned extension requiring their own schemas and deterministic checks. Microsoft Foundry clarifies/extracts/explains; Mastercard Verifiable Intent signs/verifies authorization; our backend enforces comparisons against the signed merchant offer. AI never approves a purchase.

The supplied code is a tested OFFLINE prototype, not finished live Foundry integration or a complete app. Continue it rather than discarding it. Local safe-stop check: 33 tests passed. The AI session brief lists known parsing gaps.

Shared local skills do not transfer credentials, cloud access, browser control, or tools into Devin Cloud. If running remotely, use the supplied source ZIP or Git bundle; the branch has not been pushed. No secrets are included. Treat historical design/implementation plans as background; this handoff contains the latest scope and status. Victor clarified he intended the implementation to continue in Devin and asked Codex to stop after preserving the partial work.
