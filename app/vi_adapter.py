"""Adapter over Mastercard's Verifiable Intent (VI) SDK for flight purchases.

Demo keys, merchant-JWT pattern, checkout hash and role presentations are adapted from
verifiable-intent/examples/helpers.py and autonomous_flow.py (Apache-2.0,
https://github.com/agent-intent/verifiable-intent). All keys here are fixed DEMO keys, not secrets.

Why this exists: the decision must rest on (a) the requirements the traveler approved, signed into
the user's L2 mandate, and (b) the itinerary in the MERCHANT-signed checkout_jwt - never on what the
shopping agent says. This module issues those credentials and verifies them; it never decides PASS/HOLD.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field

from cryptography.hazmat.primitives.asymmetric import ec
from verifiable_intent import Constraint
from verifiable_intent.crypto.disclosure import _b64url_encode, build_selective_presentation, hash_bytes
from verifiable_intent.crypto.sd_jwt import SdJwt, decode_sd_jwt, resolve_disclosures
from verifiable_intent.crypto.signing import (
    _jwt_decode_parts,
    _jwt_encode,
    es256_verify,
    private_key_to_jwk,
    public_key_to_jwk,
)
from verifiable_intent.issuance.agent import create_layer3_checkout, create_layer3_payment
from verifiable_intent.issuance.issuer import create_layer1
from verifiable_intent.issuance.user import create_layer2_autonomous
from verifiable_intent.models.agent_mandate import (
    CheckoutL3Mandate,
    FinalCheckoutMandate,
    FinalPaymentMandate,
    PaymentL3Mandate,
)
from verifiable_intent.models.constraints import (
    AllowedMerchantConstraint,
    AllowedPayeeConstraint,
    CheckoutLineItemsConstraint,
    PaymentAmountConstraint,
)
from verifiable_intent.models.issuer_credential import IssuerCredential
from verifiable_intent.models.user_mandate import CheckoutMandate, MandateMode, PaymentMandate, UserMandate
from verifiable_intent.verification.chain import verify_chain

from app.models import ApprovedRequirements, FlightOffer, Segment

# Category-neutral on purpose: the same constraint type carries any category's approved requirements
# (flights today; hotels, retail, subscriptions are roadmap). The `category` field says which.
CONSTRAINT_TYPE = "urn:intent-judge:requirements"

# --------------------------------------------------------------------------- demo keys
@dataclass
class KeyPair:
    private_key: ec.EllipticCurvePrivateKey
    public_jwk: dict
    kid: str

    @property
    def public_key(self) -> ec.EllipticCurvePublicKey:
        return self.private_key.public_key()


def _key_from_d(d_int: int, kid: str) -> KeyPair:
    priv = ec.derive_private_key(d_int, ec.SECP256R1())
    return KeyPair(priv, public_key_to_jwk(priv), kid)


# Fixed private values - NOT secret, demo/test keys only (same as the VI examples).
ISSUER = _key_from_d(0x1A2B3C4D5E6F708192A3B4C5D6E7F80112233445566778899AABBCCDDEEFF01, "mastercard-issuer-key-1")
USER = _key_from_d(0x2B3C4D5E6F708192A3B4C5D6E7F80112233445566778899AABBCCDDEEFF0102, "user-device-key-1")
AGENT = _key_from_d(0x3C4D5E6F708192A3B4C5D6E7F80112233445566778899AABBCCDDEEFF010203, "agent-key-1")
MERCHANT = _key_from_d(0x4D5E6F708192A3B4C5D6E7F80112233445566778899AABBCCDDEEFF01020304, "merchant-key-1")

MERCHANTS = [{"id": "merchant-skyways", "name": "SkyWays Air", "website": "https://skyways.example"}]
PAYMENT_INSTRUMENT = {"type": "mastercard.srcDigitalCard", "id": "demo-card-0001", "description": "Mastercard **** 1234 (synthetic)"}


# --------------------------------------------------------------------------- data classes
@dataclass
class CredentialBundle:
    l1: SdJwt
    l2: SdJwt
    l2_ser: str
    requirement_set_id: str
    max_total_cents: int
    currency: str


@dataclass
class VerifiedOffer:
    offer: FlightOffer | None
    vi_chain_valid: bool
    merchant_signature_valid: bool
    errors: list[str] = field(default_factory=list)
    signed_requirements: dict | None = None


# --------------------------------------------------------------------------- issuance
def issue_credentials(req: ApprovedRequirements, acceptable_offers: list[tuple[str, str]] | None = None) -> CredentialBundle:
    """Issue L1 (issuer) + L2 (user-signed mandate carrying the approved requirements).

    The approved requirements travel as the custom constraint ``urn:intent-judge:requirements`` (with ``category``),
    signed by the user key, so the agent cannot silently drop e.g. "nonstop".
    ``acceptable_offers`` is a list of (offer_id, title); defaults to the fixture offers.
    """
    if req.category != "flight":
        raise ValueError("Only the flight schema has deterministic checks in this demo")
    now = int(time.time())
    if acceptable_offers is None:
        from app.fixtures_loader import all_offer_ids

        acceptable_offers = all_offer_ids()
    items = [{"id": oid, "title": title} for oid, title in acceptable_offers]

    l1 = create_layer1(
        IssuerCredential(
            iss="https://issuer.example", sub="traveler-demo-001", iat=now, exp=now + 86400,
            aud="https://wallet.example.com", cnf_jwk=USER.public_jwk, email="alex.traveler@example.com",
            pan_last_four="1234", scheme="Mastercard",
        ),
        ISSUER.private_key,
    )
    flight_req = Constraint(
        type=CONSTRAINT_TYPE,
        extra_fields={
            "category": req.category,
            "requirement_set_id": req.requirement_set_id,
            "origin_airports": req.origin_airports,
            "destination_airports": req.destination_airports,
            "depart_date": req.depart_date.isoformat(),
            "depart_window": req.depart_window and {"earliest": req.depart_window.earliest.isoformat(), "latest": req.depart_window.latest.isoformat()},
            "arrive_by": req.arrive_by and req.arrive_by.isoformat(),
            "max_stops": req.max_stops,
            "max_total_cents": req.max_total_cents,
            "currency": req.currency,
            "cabin": req.cabin,
            "refundable_required": req.refundable_required,
            "passengers": req.passengers,
            "approved_at": req.model_dump(mode="json")["approved_at"],
            "approved_by_traveler": req.approved_by_traveler,
        },
    )
    mandate = UserMandate(
        nonce=str(uuid.uuid4()), aud="https://agent.example", iat=now, iss="https://wallet.example.com", exp=now + 86400,
        mode=MandateMode.AUTONOMOUS,
        sd_hash=hash_bytes(l1.serialize().encode("ascii")),
        prompt_summary=req.source_text,  # informational only; decisions never read it
        checkout_mandate=CheckoutMandate(
            vct="mandate.checkout.open.1", cnf_jwk=AGENT.public_jwk, cnf_kid=AGENT.kid,
            constraints=[
                AllowedMerchantConstraint(allowed=MERCHANTS),
                CheckoutLineItemsConstraint(items=[{"id": "line-item-1", "acceptable_items": items, "quantity": 1}]),
                flight_req,
            ],
        ),
        payment_mandate=PaymentMandate(
            vct="mandate.payment.open.1", cnf_jwk=AGENT.public_jwk, cnf_kid=AGENT.kid,
            payment_instrument=PAYMENT_INSTRUMENT, risk_data={"device_id": "demo-device"},
            constraints=[
                PaymentAmountConstraint(currency=req.currency, min=0, max=req.max_total_cents),
                AllowedPayeeConstraint(allowed=MERCHANTS),
            ],
        ),
        merchants=MERCHANTS,
        acceptable_items=items,
    )
    l2 = create_layer2_autonomous(mandate, USER.private_key)
    return CredentialBundle(l1, l2, l2.serialize(), req.requirement_set_id, req.max_total_cents, req.currency)


def tamper_l2(bundle: CredentialBundle) -> CredentialBundle:
    """Flip one character in the L2 signature (scenario 12 / demo toggle)."""
    base, *rest = bundle.l2_ser.split("~")
    flipped = base[:-3] + ("A" if base[-3] != "A" else "B") + base[-2:]
    return CredentialBundle(bundle.l1, bundle.l2, "~".join([flipped, *rest]), bundle.requirement_set_id, bundle.max_total_cents, bundle.currency)


def signed_requirements(bundle: CredentialBundle) -> dict | None:
    """Read the approved requirements back out of the (user-signed) L2 - evidence only."""
    claims = resolve_disclosures(decode_sd_jwt(bundle.l2_ser))
    for delegate in claims.get("delegate_payload", []):
        if isinstance(delegate, dict) and delegate.get("vct") == "mandate.checkout.open.1":
            for c in delegate.get("constraints", []):
                if c.get("type") == CONSTRAINT_TYPE:
                    return c
    return None


# --------------------------------------------------------------------------- merchant
def merchant_sign_offer(offer: FlightOffer, signer: KeyPair | None = None, note: str | None = None) -> str:
    """Merchant signs a checkout_jwt whose payload carries the itinerary (schema: docs/06).

    ``signer`` defaults to the merchant key; pass another key to simulate a forged offer (scenario 12).
    ``note`` simulates free text inside merchant data (prompt-injection scenario) - it is ignored by the parser.
    Fields that are None are omitted so the rules engine sees them as missing.
    """
    now = int(time.time())
    item: dict = {
        "sku": offer.offer_id, "type": "air_itinerary", "category": offer.category, "quantity": 1,
        "segments": [
            {"carrier": s.carrier, "flight_number": s.flight_number, "from": s.from_airport, "to": s.to_airport,
             "depart_local": s.depart_local.isoformat(), "arrive_local": s.arrive_local.isoformat()}
            for s in offer.segments
        ],
    }
    for key, value in (("passengers", offer.passengers), ("cabin", offer.cabin), ("refundable", offer.refundable)):
        if value is not None:
            item[key] = value
    if note:
        item["note"] = note
    total: dict = {"includes_taxes_and_fees": True}
    if offer.currency is not None:
        total["currencyCode"] = offer.currency
    if offer.total_cents is not None:
        total["amount_cents"] = offer.total_cents
    payload = {
        "iss": MERCHANTS[0]["website"], "sub": "cart_checkout", "iat": now, "exp": now + 3600,
        "merchant": {"id": offer.merchant_id, "name": offer.merchant_name},
        "cart": {"items": [item], "total": total},
    }
    keys = signer or MERCHANT
    return _jwt_encode({"alg": "ES256", "typ": "JWT", "kid": keys.kid}, payload, keys.private_key)


def checkout_hash(checkout_jwt: str) -> str:
    return _b64url_encode(hashlib.sha256(checkout_jwt.encode("utf-8")).digest())


def _verify_merchant_signature(checkout_jwt: str) -> tuple[bool, dict | None]:
    """Check the merchant ES256 signature ourselves; only then is the payload trusted."""
    try:
        header, payload, signature = _jwt_decode_parts(checkout_jwt)
        signing_input = checkout_jwt.rsplit(".", 1)[0].encode("ascii")
        ok = header.get("alg") == "ES256" and es256_verify(signing_input, signature, MERCHANT.public_key)
        ok = ok and isinstance(payload, dict)
        if ok:
            expiry, issued = payload.get("exp"), payload.get("iat")
            ok = (type(expiry) is int and type(issued) is int
                  and issued <= time.time() + 300 and expiry >= time.time()
                  and payload.get("iss") == MERCHANTS[0]["website"])
        return bool(ok), (payload if ok else None)
    except Exception:
        return False, None


def _offer_from_payload(payload: dict, offer_hash: str) -> FlightOffer:
    item = payload["cart"]["items"][0]
    total = payload["cart"].get("total", {})
    return FlightOffer(
        category=item.get("category", "flight"), offer_id=item["sku"], merchant_id=payload["merchant"]["id"], merchant_name=payload["merchant"]["name"],
        segments=[
            Segment(carrier=s["carrier"], flight_number=s["flight_number"], from_airport=s["from"], to_airport=s["to"],
                    depart_local=s["depart_local"], arrive_local=s["arrive_local"])
            for s in item["segments"]
        ],
        total_cents=total.get("amount_cents") if total.get("includes_taxes_and_fees", False) else None,
        currency=total.get("currencyCode") or None, cabin=item.get("cabin"), refundable=item.get("refundable"),
        passengers=item.get("passengers"), offer_hash=offer_hash,
    )


# --------------------------------------------------------------------------- agent + verification
def _find_disclosure(sd_jwt: SdJwt, predicate) -> str | None:
    for disc_str, disc_val in zip(sd_jwt.disclosures, sd_jwt.disclosure_values):
        value = disc_val[-1] if disc_val else None
        if predicate(value):
            return disc_str
    return None


def _role_presentations(l2: SdJwt) -> tuple[str, str]:
    """(checkout-only, payment-only) L2 views - merchant never sees payment data and vice versa."""
    checkout_idx: list[int] = []
    payment_idx: list[int] = []
    for idx, disc_val in enumerate(l2.disclosure_values):
        value = disc_val[-1] if disc_val else None
        if not isinstance(value, dict):
            continue
        vct = value.get("vct")
        if vct == "mandate.checkout.open.1" or ("id" in value and "title" in value):
            checkout_idx.append(idx)
        elif vct == "mandate.payment.open.1" or ("name" in value and "website" in value):
            payment_idx.append(idx)
    return l2.serialize(include_disclosures=checkout_idx), l2.serialize(include_disclosures=payment_idx)


def _flight_requirements_from_verified_claims(claims: dict) -> dict:
    """Read exactly one approved requirements extension after serialized chain verification."""
    constraints = [
        constraint
        for delegate in claims.get("delegate_payload", [])
        if isinstance(delegate, dict) and delegate.get("vct") == "mandate.checkout.open.1"
        for constraint in delegate.get("constraints", [])
        if constraint.get("type") == CONSTRAINT_TYPE
    ]
    if len(constraints) != 1:
        raise ValueError("Exactly one signed requirements constraint is required")
    required = {k: v for k, v in constraints[0].items() if k != "type"}
    if required.get("category") != "flight":
        raise ValueError("Unsupported signed requirements category")
    return required


def requirements_match(req: ApprovedRequirements, signed: dict | None) -> bool:
    """Compare rule authority fields, not the informational original words or summary."""
    if signed is None:
        return False
    expected = req.model_dump(mode="json", exclude={"source_text"})
    return expected == signed


def verify_and_extract(bundle: CredentialBundle, checkout_jwt: str) -> VerifiedOffer:
    """Simulate the agent building L3a/L3b from the merchant's checkout_jwt, then verify everything.

    Returns the FlightOffer parsed ONLY from the merchant-signed payload. Any failure -> flags False
    (the rules engine turns that into BLOCK). L3 credentials are short-lived (5 min), so this is called
    per check, not at approval time.
    """
    errors: list[str] = []
    sig_ok, payload = _verify_merchant_signature(checkout_jwt)
    c_hash = checkout_hash(checkout_jwt)
    chain_ok = False
    approved = None
    try:
        now = int(time.time())
        l2_ser = bundle.l2_ser
        l2_base = l2_ser.split("~")[0]
        l2 = decode_sd_jwt(l2_ser)

        if not sig_ok or payload is None:
            raise ValueError("merchant signature invalid; untrusted checkout data was not read")
        sku = payload["cart"]["items"][0]["sku"]
        amount = payload["cart"].get("total", {}).get("amount_cents", 0)

        payment_disc = _find_disclosure(l2, lambda v: isinstance(v, dict) and v.get("vct") == "mandate.payment.open.1")
        checkout_disc = _find_disclosure(l2, lambda v: isinstance(v, dict) and v.get("vct") == "mandate.checkout.open.1")
        merchant_disc = _find_disclosure(l2, lambda v: isinstance(v, dict) and v.get("id") == MERCHANTS[0]["id"])
        item_disc = _find_disclosure(l2, lambda v: isinstance(v, dict) and v.get("id") == sku)
        if not all([payment_disc, checkout_disc, merchant_disc, item_disc]):
            raise ValueError(f"offer {sku!r} is not among the mandate's acceptable items")

        nonce = str(uuid.uuid4())
        l3a = create_layer3_payment(
            PaymentL3Mandate(
                nonce=nonce, aud="https://network.example", iat=now, iss="https://agent.example", exp=now + 300,
                final_payment=FinalPaymentMandate(transaction_id=c_hash, payee=MERCHANTS[0],
                                                  payment_amount={"currency": bundle.currency, "amount": amount},
                                                  payment_instrument=PAYMENT_INSTRUMENT),
                final_merchant=MERCHANTS[0],
            ),
            AGENT.private_key, l2_base, payment_disc, merchant_disc,
        )
        l3b = create_layer3_checkout(
            CheckoutL3Mandate(
                nonce=nonce, aud=MERCHANTS[0]["website"], iat=now, iss="https://agent.example", exp=now + 300,
                final_checkout=FinalCheckoutMandate(checkout_jwt=checkout_jwt, checkout_hash=c_hash),
            ),
            AGENT.private_key, l2_base, checkout_disc, item_disc,
        )

        l2_checkout_only, _ = _role_presentations(l2)
        l2_payment_ser = build_selective_presentation(l2_base, [payment_disc, merchant_disc])
        l2_checkout_ser = build_selective_presentation(l2_base, [checkout_disc, item_disc])
        l1_ser = bundle.l1.serialize()
        l1_parsed = decode_sd_jwt(l1_ser)

        merchant_side = verify_chain(
            l1_parsed, decode_sd_jwt(l2_checkout_only), l3_checkout=l3b, issuer_public_key=ISSUER.public_key,
            l1_serialized=l1_ser, l2_serialized=l2_ser, l2_checkout_serialized=l2_checkout_ser,
        )
        network_side = verify_chain(
            l1_parsed, decode_sd_jwt(l2_ser), l3_payment=l3a, issuer_public_key=ISSUER.public_key,
            l1_serialized=l1_ser, l2_serialized=l2_ser, l2_payment_serialized=l2_payment_ser,
        )
        errors += merchant_side.errors + network_side.errors
        chain_ok = merchant_side.valid and network_side.valid
        if chain_ok:
            approved = _flight_requirements_from_verified_claims(network_side.l2_claims)
    except Exception as exc:  # any failure is untrusted -> BLOCK path
        chain_ok = False
        approved = None
        errors.append(f"{type(exc).__name__}: {exc}")

    offer = None
    if sig_ok and payload:
        try:
            offer = _offer_from_payload(payload, c_hash)
            if offer.category != "flight":
                raise ValueError("Unsupported signed offer category")
        except Exception as exc:
            chain_ok = False
            approved = None
            errors.append(f"Invalid signed itinerary: {type(exc).__name__}: {exc}")
    if not sig_ok:
        errors.append("merchant signature invalid")
    return VerifiedOffer(offer=offer, vi_chain_valid=chain_ok, merchant_signature_valid=sig_ok,
                         errors=errors, signed_requirements=approved)
