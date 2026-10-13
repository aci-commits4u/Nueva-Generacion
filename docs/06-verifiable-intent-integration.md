# Actual Verifiable Intent integration

Status: proposed project integration grounded in the inspected SDK. Do not replace the SDK with a mocked `chain_valid=true` in the demonstrator.

## Credential responsibilities

Use autonomous VI for the principal comparison: L1 establishes issuer-to-user trust, L2 carries the user-approved checkout/payment mandates, and split L3a/L3b carries agent payment/checkout fulfillment. Immediate mode represents a final checkout the user confirms directly. [SDK issuance exports](https://github.com/agent-intent/verifiable-intent/blob/356c29635f1c44df7de02edb58699ca9f29bece6/src/verifiable_intent/__init__.py).

For the prototype, all participants and signing roles are synthetic. Our app simulates the customer approval action and signs with a synthetic user key. That proves the fixture's cryptographic chain, not that a real bank authenticated a real cardholder.

Use `create_layer1`, `create_layer2_autonomous`, `create_layer3_checkout`, and `create_layer3_payment`. Use the SDK's signature/binding verification rather than reimplementing the delegation chain. An exact-cart exception may use fresh autonomous authorization or the documented immediate path where appropriate.

## Registered constraint vocabulary

The inspected specification lists these eight types:

```text
mandate.checkout.allowed_merchants
mandate.checkout.line_items
mandate.payment.allowed_payees
mandate.payment.amount_range
mandate.payment.budget
mandate.payment.recurrence
mandate.payment.agent_recurrence
mandate.payment.reference
```

Use native types for applicable native restrictions. Explicitly map the approved USD price ceiling to `PaymentAmountConstraint`. Product restrictions need actual approved item identities and quantity semantics; listing candidate products is not equivalent to checking their flight attributes.

Custom types are supported by the specification's extension model, but a particular verifier must know how to evaluate them. [Constraint specification](https://github.com/agent-intent/verifiable-intent/blob/356c29635f1c44df7de02edb58699ca9f29bece6/spec/constraints.md).

## Custom requirements carried in authorization

For flights, include the full `ApprovedRequirements` record in `urn:intent-judge:flight-requirements`, with a pinned schema/profile version, requirement-set ID/revision/digest, approved values, and explicit no-preference choices. Use the SDK `Constraint` representation to preserve the application fields. [Constraint models](https://github.com/agent-intent/verifiable-intent/blob/356c29635f1c44df7de02edb58699ca9f29bece6/src/verifiable_intent/models/constraints.py).

The verified, resolved L2 object must agree with the server's immutable approved record. An agent-submitted replacement requirement object is never authoritative. For other profiles use collision-resistant custom types with the same approval contract.

## Composite verifier: proposed extension design

The stock `check_constraints` function has fixed built-in dispatch and no custom validator callback in the inspected signature. Calling it on the entire open-mandate constraint array containing our URN correctly rejects that unknown type. Calling it permissively with `is_open_mandate=False` does not implement the domain condition. [Checker source](https://github.com/agent-intent/verifiable-intent/blob/356c29635f1c44df7de02edb58699ca9f29bece6/src/verifiable_intent/verification/constraint_checker.py).

Our adapter should implement a disclosed composite verifier:

1. Verify the complete signed chain and all expected disclosures and references. Preserve the signed constraint array exactly for evidence.
2. Enumerate each constraint instance and assign one evaluator from a fixed, reviewed registry.
3. Give built-in constraints to VI's checker with strict handling and the actual autonomous/open semantics. Resolve disclosed allowlists before checking.
4. Give explicitly recognized application constraints to our pure deterministic domain engine, using verified merchant facts and pinned profile semantics.
5. Unknown or unsupported types prevent execution. No silently dropped constraint is allowed.
6. Combine detailed findings through `rules_engine.py`. PASS requires all mandatory verifications and applicable checks to succeed.

Partitioning is an application-level dispatch mechanism after signature verification, not a modified signed credential or a claim that stock VI understands our URN. Retain an instance-level ledger of original constraints and evaluator results, so duplicate types or omitted instances cannot disappear behind a set of type names.

This extension must be proven in integration tests. It does not establish interoperability with an unmodified third-party verifier, which may reject the same custom constraint. A deployment partner must agree on the profile and evaluator. Do not patch or monkeypatch the SDK merely to report success.

Budget/recurrence responsibilities are unavailable for the first single-purchase demo unless real stateful enforcement is implemented. Mark them unsupported and hold, rather than accepting the stock local checker's `checked` marker as complete enforcement.

## Chain verification is one gate

`verify_chain` checks credential integrity and bindings; separate evaluation checks purchasing restrictions. Supply a trusted issuer public key, actual serialized presentations, and appropriate expected audience/nonce values. Inspect performed and skipped verification details; missing necessary disclosures cannot be hidden by a valid boolean. [Chain verifier](https://github.com/agent-intent/verifiable-intent/blob/356c29635f1c44df7de02edb58699ca9f29bece6/src/verifiable_intent/verification/chain.py).

Do not use `skip_issuer_verification=True` in the application. Role-specific selective disclosure is legitimate, but a party cannot claim to have checked a condition for which it did not receive the needed data.

## Merchant offer trust

Our checkout profile requires a merchant-signed JWT using an allowed algorithm and a key from a trusted merchant registry. Verify the signature, merchant identity, issue/expiry times, and schema before deriving itinerary facts. A key or issuer URL supplied by the agent is not a trust root.

VI's draft makes the checkout envelope implementation-defined and gives signature-verification guidance. Intent Judge deliberately defines a stricter application contract. [Credential format, section 6.3](https://github.com/agent-intent/verifiable-intent/blob/356c29635f1c44df7de02edb58699ca9f29bece6/spec/credential-format.md#63-checkout_jwt--checkout-object-representation).

Use the exact checkout JWT string to compute `offer_hash = B64U(SHA-256(ASCII(checkout_jwt)))`. It must agree with the checkout hash and payment transaction ID. These bindings are checked by the SDK's [integrity functions](https://github.com/agent-intent/verifiable-intent/blob/356c29635f1c44df7de02edb58699ca9f29bece6/src/verifiable_intent/verification/integrity.py).

Also compare signed checkout total/currency with final payment total/currency. A shared hash alone does not prove that independently represented totals agree. Merchant identity, payee, products, quantity, and passenger/trip scope must have consistent mappings.

## Exceptions and new mandates

A domain exception must be bound into user-signed application authorization for the exact offer, requirement revision, check ID, and accepted value. The composite evaluator recognizes only that explicit authorization. Preserve both the original requirement and the exception.

An exception above a native VI price maximum requires new native authorization, not a bypass. Prefer a narrowly scoped authorization for the exact accepted cart where the selected mode supports it. Retain original and amended credentials in evidence and re-run every verification.

Invalid signatures and hash/identity substitutions remain BLOCK. Expired or incomplete authorizations cannot be waived with a business exception; obtain valid records and check again.

## Dependency baseline

When implementation begins, pin the inspected SDK commit:

```text
verifiable-intent @ git+https://github.com/agent-intent/verifiable-intent.git@356c29635f1c44df7de02edb58699ca9f29bece6
```

Upstream changes require renewed adapter verification. The inspected package requires Python 3.10+ and `cryptography>=42.0`; our project baseline remains Python 3.11+. [Package metadata](https://github.com/agent-intent/verifiable-intent/blob/356c29635f1c44df7de02edb58699ca9f29bece6/pyproject.toml).
