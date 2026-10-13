# Adapting the layer to another task

The working method is a **reviewed domain profile plus a trusted offer adapter**. Flights and hotels already reuse approval, signing, checks, exceptions, purchase gating, evidence, storage and the question renderer. The model receives the selected profile's field types, meanings and questions. A prompt proposes values; the profile defines what can actually be enforced.

## A field in the actual format

This field from `profiles/hotel.json` needs no hotel-specific branch in the rules engine:

```json
{
  "breakfast": {
    "type": "boolean",
    "op": "eq",
    "fact": "breakfast",
    "label": "Breakfast included",
    "question": "Must breakfast be included?",
    "exception_allowed": true,
    "required": false
  }
}
```

The AI can propose `true` only with a source quotation. The customer chooses true, false, or explicitly no preference. Approval stores that value under the profile digest and custom VI constraint. A merchant-signed offer must contain a real boolean fact to match it. Missing or ill-typed facts hold; a mismatch fails. Eligible consent records the exact accepted value and signed-offer hash.

## Integration checklist

1. Define purchasing semantics: units, total price, currency, required task identity, fact completeness, and whether a business difference can be accepted. Start with existing types/operators; do not execute customer-supplied predicates.
2. Add a reviewed JSON profile with a stable ID, version and custom constraint URN. Include every field's type, operator, fact mapping, traveler label and question. Profile digest changes invalidate earlier approvals.
3. Define the merchant's signed data contract and normalization. For flights this derives route, connections and duration from complete, continuous signed segments. For hotels it checks signed room facts. An agent's claim that “this matches” is never a fact source.
4. Register the domain in the trusted server allowlists and request domain enum. The current prototype intentionally exposes only `flight`, `hotel`, and `general`; it is not a runtime profile uploader. Add the corresponding UI tab/sample metadata.
5. Supply a separate synthetic demo commerce adapter or a real contracted adapter. Discovery/payment integration does not become approval authority. Pin the merchant trust root independently from offer text.
6. Add boundary, missing-fact, signature, unimplemented-condition, exact-consent and backend refusal cases. Verify live extraction with a small labeled evaluation set and visible failure handling.

This is low-code adoption, not zero-code universal enforcement. An existing operator and trustworthy mapped fact reuse the engine immediately. A new calculation, identity model or protocol needs reviewed implementation. The current profile allowlists and synthetic trust registry are deliberately closed.

## Handling requirements outside the schema

Preserve them as unsupported. The review screen displays them and permits adding missed conditions. Approving the request does not make those conditions executable. General mode provides broad intake with a shared price field, while unknown qualities such as “ethical” or “comfortable” hold checkout.

To support a condition later, define an observable signed fact and precise test semantics, version the profile, rerun the acceptance checks and obtain a new approval. Do not convert an unresolved condition into “no preference” or write a prompt that claims to enforce it.

The earlier richer profile DSL in [the original proposal](05-domain-profiles.md) remains an extension design. The executable format is the JSON files under `profiles/`, interpreted by `app/profile_registry.py` and `app/rules_engine.py`.
