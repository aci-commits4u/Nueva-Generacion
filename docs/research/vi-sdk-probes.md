# VI SDK research execution record

Date: October 13, 2026.

Repository snapshot: [`356c29635f1c44df7de02edb58699ca9f29bece6`](https://github.com/agent-intent/verifiable-intent/tree/356c29635f1c44df7de02edb58699ca9f29bece6).

The SDK was cloned into `/tmp/intent-judge-vi-research`. Research dependencies were supplied in an isolated `uv run --no-project` environment. No Intent Judge application or tests were implemented during this research.

## Focused upstream tests

Executed from the SDK clone:

```sh
uv run --no-project --with 'cryptography>=42' --with 'pytest>=8' -- python -m pytest -q tests/test_constraint_checking.py tests/test_new_constraints.py tests/test_chain_binding.py tests/test_autonomous_flow.py tests/test_verification_hardening.py
```

Observed result: **135 passed in 0.16s**, process exit code 0.

This is a selected upstream suite, not the entire upstream suite and not application acceptance verification.

## Direct checker observations

| Probe | Inputs/settings | Observed output |
|---|---|---|
| Custom URN, default permissive | `urn:intent-judge:flight-requirements`, empty fulfillment, default open flag false | `satisfied=true`, no checked types, URN listed in `skipped` |
| Custom URN, strict | Same constraint, `mode=STRICT` | `satisfied=false`, unknown-type violation |
| Custom URN, autonomous/open | Same constraint, permissive mode, `is_open_mandate=True` | `satisfied=false`, unknown-type violation; no skip |
| Amount over maximum | USD max 30000; amount 31240; strict/open | `satisfied=false`, amount-above-maximum violation |
| Budget requiring external state | USD budget max 30000; amount 999999; strict/open | `satisfied=true`, budget listed in `checked` |

The last result is explained by the code's delegation of budget enforcement to the network. It is not evidence that such a purchase meets the budget. See [checker source](https://github.com/agent-intent/verifiable-intent/blob/356c29635f1c44df7de02edb58699ca9f29bece6/src/verifiable_intent/verification/constraint_checker.py).

### Reproduce the direct probes

From the pinned clone:

```sh
uv run --no-project --with 'cryptography>=42' -- python - <<'PY'
import sys
sys.path.insert(0, "src")
from verifiable_intent import check_constraints, StrictnessMode

custom = [{"type": "urn:intent-judge:flight-requirements", "max_stops": 0}]
for options in ({}, {"mode": StrictnessMode.STRICT}, {"is_open_mandate": True}):
    print(check_constraints(custom, {}, **options))

print(check_constraints(
    [{"type": "mandate.payment.amount_range", "currency": "USD", "max": 30000}],
    {"payment_amount": {"amount": 31240, "currency": "USD"}},
    mode=StrictnessMode.STRICT, is_open_mandate=True,
))
print(check_constraints(
    [{"type": "mandate.payment.budget", "currency": "USD", "max": 30000}],
    {"payment_amount": {"amount": 999999, "currency": "USD"}},
    mode=StrictnessMode.STRICT, is_open_mandate=True,
))
PY
```

## Autonomous example

Executed the upstream `examples/autonomous_flow.py` using the isolated cryptography environment. Exit code 0. Observed output included `Chain valid: True` and `Constraints satisfied: True`.

This is upstream's synthetic purchase example, not our flight demo. The reference example's permissive defaults are not a complete application authorization policy.

## Chain-valid transaction above its native price ceiling

Used the upstream autonomous test fixture builder, changing only its payment maximum from 40000 to 20000 before signing the fixture. The fixture still authorizes an allowed product and produces payment amount 27999. Verified the correctly signed full chain and separately checked that amount against the signed bound.

Observed:

```json
{
  "probe": "signed_chain_over_authorized_price",
  "chain_valid": true,
  "chain_errors": [],
  "amount_constraint_satisfied": false,
  "violations": ["Amount exceeds maximum: 27999 > 20000 USD"]
}
```

This demonstrates API responsibility separation, not a claim that a fully configured VI verifier approves an over-limit purchase.

### Reproduce the chain probe

The following modifies the fixture function in memory; it does not edit upstream files or tamper with an already signed credential.

```sh
uv run --no-project --with 'cryptography>=42' --with 'pytest>=8' -- python - <<'PY'
import ast
import inspect
import runpy
import sys
sys.path[:0] = ["src", "examples", "tests"]
from verifiable_intent import verify_chain, check_constraints, StrictnessMode

scope = runpy.run_path("tests/test_autonomous_flow.py")
tree = ast.parse(inspect.getsource(scope["_build_full_chain"]))
class ChangeLimit(ast.NodeTransformer):
    def visit_Constant(self, node):
        if node.value == 40000:
            return ast.copy_location(ast.Constant(value=20000), node)
        return node
tree = ast.fix_missing_locations(ChangeLimit().visit(tree))
exec(compile(tree, "research-probe", "exec"), scope)
c = scope["_build_full_chain"]()
chain = verify_chain(
    c["l1"], c["l2"], l3_payment=c["l3a"], l3_checkout=c["l3b"],
    issuer_public_key=c["issuer"].public_key,
    l1_serialized=c["l1_ser"], l2_serialized=c["l2_ser"],
    l2_payment_serialized=c["l2_payment_ser"],
    l2_checkout_serialized=c["l2_checkout_ser"],
)
policy = check_constraints(
    [{"type": "mandate.payment.amount_range", "currency": "USD",
      "min": 10000, "max": 20000}],
    {"payment_amount": {"currency": "USD", "amount": 27999}},
    mode=StrictnessMode.STRICT, is_open_mandate=True,
)
print("chain_valid:", chain.valid, "amount_satisfied:", policy.satisfied)
print(policy.violations)
assert chain.valid and not policy.satisfied
PY
```

## Limits and next checks

These probes do not test our future composite verifier, signed flight schema, customer approval UI, exception signing, API enforcement, hotel profile, or Foundry client. Those require the application acceptance suite.

The probes establish why those integrations must inspect actual results instead of treating an SDK chain-valid or checked-type marker as universal purchase approval.
