# Devin session 3 — vendor evidence and neutral dispute packet

You own packet assembly, not model language or API/frontend. Work on `devin/vendor-evidence` from the saved victor/rules snapshot in its own worktree. You are not alone: never revert others' edits. Read AGENTS.md, DEVIN-HANDOFF.md, docs/handoff/README.md, docs/07-rules-engine-spec.md, docs/11-security-and-responsible-ai.md, and app/models.py. Do not edit shared models/fixtures/VI adapter, foundry_client.py, conversation.py, rules_engine.py, main.py, store.py, or web/.

Own `app/evidence.py`, `tests/test_evidence.py`, and `docs/handoff/results/evidence.md`.

Implement the fixed interface:

```python
build_packet(purchase, dispute_claim, decision, req, offer, exceptions,
             narrative=None) -> EvidencePacket
```

purchase supplies purchase_id by mapping or attribute. Do not invent a shared Purchase model. Preserve final_decision='dispute analyst'. Responsibility/reason code are recommendations computed by code, never from LLM narrative. Existing prototype reason codes are not certified or legal determinations.

Use the existing recommendation table conservatively. Assemble original approved values, verified signed-offer fields/hash, rule checks, and matching exceptions. Validate id/hash consistency before treating an exception as consent. Wrong offer/decision/value cannot appear as accepted evidence. Model-written narrative cannot override a recommendation or invent facts. A free-text allegation about merchant delivery is not proof of different delivery; without relevant evidence recommend unclear rather than merchant fault. Distinguish integrity failures, platform-enforcement bypass supported by records, and an explicitly accepted deviation. Do not promise the vendor wins a chargeback or receives liability protection.

The AI session exposes trace_for_requirements(requirement_set_id), an immutable copied application trace. Preserve a clean seam: document an evidence response envelope containing existing `EvidencePacket` plus a separate `conversation_trace` attachment; API session assembles it. Do not change EvidencePacket silently or make evidence.py depend on mutable global conversation state. The trace contains literal words, follow-up answers, field interpretations, and approved snapshot. It is NOT a user-signed transcript. Application-recorded exceptions are NOT newly signed VI authorizations. Include those labels in your rationale/handoff.

Tests can construct genuine existing Pydantic req/offer/Decision fixtures directly while rules session runs; no fake implementation of another session's module. Write failing tests for matching packet, exact accepted deviation, wrong-hash/decision/value rejection, final analyst authority, narrative non-authority, and insufficient delivery evidence. Use copies so constructing a packet does not mutate source records.

Done: working packet builder, tests and entire suite green, exact return contract, concise results/evidence.md with actual commit/test proof and trace-envelope instructions for session 4. Commit only owned files; no merge/push main. The vendor evidence view belongs to Josue/API integration.
