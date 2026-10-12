"""In-memory state for the demo (no database). `reset()` makes the demo rerunnable in one click."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.models import ApprovedRequirements, Decision, ExceptionAcceptance, FlightOffer
from app.vi_adapter import CredentialBundle


@dataclass
class Purchase:
    purchase_id: str
    decision_id: str
    requirement_set_id: str
    offer_hash: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    exceptions: list[ExceptionAcceptance] = field(default_factory=list)


@dataclass
class Store:
    requirements: dict[str, ApprovedRequirements] = field(default_factory=dict)
    bundles: dict[str, CredentialBundle] = field(default_factory=dict)  # by requirement_set_id
    decisions: dict[str, Decision] = field(default_factory=dict)
    offers: dict[str, FlightOffer] = field(default_factory=dict)  # by decision_id (verified offer or empty placeholder)
    exceptions: dict[str, list[ExceptionAcceptance]] = field(default_factory=dict)  # by decision_id
    purchases: dict[str, Purchase] = field(default_factory=dict)
    checkout_jwts: dict[str, str] = field(default_factory=dict)
    decision_requirements: dict[str, ApprovedRequirements] = field(default_factory=dict)
    conversation_traces: dict[str, dict] = field(default_factory=dict)
    conversation_drafts: dict[str, dict] = field(default_factory=dict)

    def reset(self) -> None:
        for name in self.__dataclass_fields__:
            getattr(self, name).clear()


store = Store()
