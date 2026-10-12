import pytest

from app import vi_adapter as vi
from app.fixtures_loader import base_requirements, offer, scenarios


@pytest.fixture(scope="module")
def bundle():
    return vi.issue_credentials(base_requirements())


@pytest.mark.parametrize("key", ["A", "B", "C", "D", "E", "F", "G", "H"])
def test_round_trip_matches_fixture_and_chain_valid(bundle, key):
    fixture = offer(key)
    result = vi.verify_and_extract(bundle, vi.merchant_sign_offer(fixture))
    assert result.errors == []
    assert result.vi_chain_valid and result.merchant_signature_valid
    assert result.offer.model_dump(exclude={"offer_hash"}) == fixture.model_dump(exclude={"offer_hash"})


def test_offer_hash_is_checkout_hash(bundle):
    jwt = vi.merchant_sign_offer(offer("B"))
    result = vi.verify_and_extract(bundle, jwt)
    assert result.offer.offer_hash == vi.checkout_hash(jwt)


def test_price_over_budget_is_not_a_chain_failure(bundle):
    # Scenario 8 must be a HOLD (rules engine), not a BLOCK: the chain itself is still valid.
    result = vi.verify_and_extract(bundle, vi.merchant_sign_offer(offer("H")))
    assert result.vi_chain_valid and result.offer.total_cents == 30001


def test_tampered_l2_is_invalid(bundle):
    result = vi.verify_and_extract(vi.tamper_l2(bundle), vi.merchant_sign_offer(offer("B")))
    assert not result.vi_chain_valid


def test_checkout_jwt_not_signed_by_merchant_is_invalid(bundle):
    forged = vi.merchant_sign_offer(offer("B"), signer=vi.AGENT)
    result = vi.verify_and_extract(bundle, forged)
    assert not result.merchant_signature_valid
    assert result.offer is None  # nothing is read from an unverified payload


def test_offer_not_in_mandate_is_untrusted(bundle):
    rogue = offer("B").model_copy(update={"offer_id": "OFFER-ROGUE"})
    result = vi.verify_and_extract(bundle, vi.merchant_sign_offer(rogue))
    assert not result.vi_chain_valid


def test_missing_fields_stay_missing(bundle):
    result = vi.verify_and_extract(bundle, vi.merchant_sign_offer(offer("F")))
    assert result.offer.refundable is None


def test_injection_note_in_merchant_data_is_ignored(bundle):
    jwt = vi.merchant_sign_offer(offer("B"), note=scenarios()[10]["injection"])
    result = vi.verify_and_extract(bundle, jwt)
    assert result.vi_chain_valid
    assert result.offer.model_dump(exclude={"offer_hash"}) == offer("B").model_dump(exclude={"offer_hash"})


def test_approved_requirements_are_signed_into_l2(bundle):
    signed = vi.signed_requirements(bundle)
    assert signed["max_stops"] == 0 and signed["max_total_cents"] == 30000
    assert signed["type"] == vi.FLIGHT_CONSTRAINT_TYPE
