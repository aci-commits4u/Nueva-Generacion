"""Load the shared scenario fixtures (app/fixtures/offers.json) into model objects."""
from __future__ import annotations

import json
from pathlib import Path

from app.models import ApprovedRequirements, FlightOffer

_PATH = Path(__file__).parent / "fixtures" / "offers.json"


def _raw() -> dict:
    return json.loads(_PATH.read_text())


def base_requirements(**override) -> ApprovedRequirements:
    return ApprovedRequirements(**{**_raw()["base_requirements"], **override})


def offer(key: str) -> FlightOffer:
    return FlightOffer(**_raw()["offers"][key])


def find_offer(ref: str) -> FlightOffer | None:
    """Look up a fixture offer by letter key ("B") or offer_id ("OFFER-B-3STOP")."""
    offers = _raw()["offers"]
    if ref in offers:
        return FlightOffer(**offers[ref])
    for data in offers.values():
        if data["offer_id"] == ref:
            return FlightOffer(**data)
    return None


def all_offer_ids() -> list[tuple[str, str]]:
    return [(o["offer_id"], f"{o['merchant_name']} {o['offer_id']}") for o in _raw()["offers"].values()]


def scenarios() -> list[dict]:
    return _raw()["scenarios"]
