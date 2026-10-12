"""Language assistance only: validated drafts and explanations, never purchase authority."""
from __future__ import annotations

import calendar
import os
import re
from datetime import date, time
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import ApprovedRequirements, Decision, EvidencePacket, ExplainResult, ExtractResult


class DraftWindow(BaseModel):
    model_config = ConfigDict(extra='forbid')
    earliest: time
    latest: time

    @model_validator(mode='after')
    def ordered(self):
        if self.earliest > self.latest or self.earliest.tzinfo or self.latest.tzinfo:
            raise ValueError('Use an ordered local-airport time window')
        return self


class DraftRequirements(BaseModel):
    """Partial drafts cannot carry approval, result, or arbitrary instruction fields."""
    model_config = ConfigDict(extra='forbid', strict=True)
    origin_airports: list[str] | None = None
    destination_airports: list[str] | None = None
    depart_date: str | None = None
    depart_window: DraftWindow | None = None
    arrive_by: str | None = None
    max_stops: Annotated[int, Field(ge=0, le=10)] | None = None
    max_total_cents: Annotated[int, Field(gt=0)] | None = None
    currency: str | None = None
    cabin: Literal['economy', 'premium_economy', 'business', 'first'] | None = None
    refundable_required: bool | None = None
    passengers: Annotated[int, Field(ge=1, le=20)] = 1

    @field_validator('origin_airports', 'destination_airports')
    @classmethod
    def airports(cls, values):
        if values is not None and (not values or any(not re.fullmatch(r'[A-Z]{3}', v) for v in values)):
            raise ValueError('Use nonempty IATA airport codes')
        return values

    @field_validator('depart_date')
    @classmethod
    def valid_date(cls, value):
        if value is not None:
            date.fromisoformat(value)
        return value

    @field_validator('arrive_by')
    @classmethod
    def valid_time(cls, value):
        if value is not None and time.fromisoformat(value).tzinfo:
            raise ValueError('Use local airport time')
        return value

    @field_validator('currency')
    @classmethod
    def valid_currency(cls, value):
        if value is not None and not re.fullmatch(r'[A-Z]{3}', value):
            raise ValueError('Use a three-letter currency')
        return value

    def fields(self) -> dict:
        values = self.model_dump(mode='json')
        if self.depart_window:
            values['depart_window'] = {
                'earliest': self.depart_window.earliest.strftime('%H:%M'),
                'latest': self.depart_window.latest.strftime('%H:%M'),
            }
        return values


def questions_for(draft: dict) -> list[str]:
    """Ask about unresolved essentials first, keeping each conversational turn short."""
    questions = []
    for field, question in (
        ('origin_airports', 'Which city or airport are you leaving from?'),
        ('destination_airports', 'Which destination city or airport do you want?'),
        ('depart_date', 'What exact departure date should I use?'),
        ('max_total_cents', 'What is your maximum total price, including taxes and fees?'),
        ('currency', 'Which currency is your price limit in?'),
    ):
        if draft.get(field) is None:
            questions.append(question)
    return questions[:2]


_LOCATIONS = {
    'nyc': ['JFK', 'LGA', 'EWR'], 'new york': ['JFK', 'LGA', 'EWR'],
    'orlando': ['MCO'], 'tampa': ['TPA'], 'boston': ['BOS'], 'miami': ['MIA'],
    'jfk': ['JFK'], 'lga': ['LGA'], 'ewr': ['EWR'], 'mco': ['MCO'], 'tpa': ['TPA'], 'bos': ['BOS'], 'mia': ['MIA'],
}
_LOCATION_RE = r'\b(' + '|'.join(sorted(_LOCATIONS, key=len, reverse=True)) + r')\b'


def _mock_draft(text: str, today: date) -> tuple[dict, str]:
    """Parse the synthetic demo vocabulary conservatively; ambiguity stays visible."""
    text = text.lower()
    draft = DraftRequirements().fields()
    notes = ['Draft only. One traveler is the demo default; review before confirming.']
    locations = list(re.finditer(_LOCATION_RE, text))
    if len(locations) >= 2:
        draft['origin_airports'] = _LOCATIONS[locations[0].group(1)]
        draft['destination_airports'] = _LOCATIONS[locations[1].group(1)]
    elif locations:
        loc = locations[0]
        field = 'origin_airports' if loc.group(1) in ('nyc', 'new york') or re.search(r'\bfrom\s*$', text[:loc.start()]) else 'destination_airports'
        draft[field] = _LOCATIONS[loc.group(1)]
    dates = set(re.findall(r'\b\d{4}-\d{2}-\d{2}\b', text))
    months = {name.lower(): n for n, name in enumerate(calendar.month_name) if name}
    months.update({name.lower(): n for n, name in enumerate(calendar.month_abbr) if name})
    for month, day, year in re.findall(r'\b(' + '|'.join(months) + r')\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(20\d{2}))?\b', text):
        try:
            dates.add(date(int(year) if year else today.year, months[month], int(day)).isoformat())
        except ValueError:
            notes.append('That date needs clarification.')
    if len(dates) == 1:
        try:
            draft['depart_date'] = date.fromisoformat(next(iter(dates))).isoformat()
        except ValueError:
            notes.append('That date needs clarification.')
    elif len(dates) > 1:
        notes.append('Multiple dates were mentioned; confirm the departure date.')
    amounts = set(int(Decimal(amount.replace(',', '')) * 100) for amount in re.findall(r'(?:\$\s*|(?:under|below|up to|budget(?: of)?|maximum(?: of)?)\s+)(\d[\d,]*(?:\.\d{1,2})?)', text))
    if len(amounts) == 1 and next(iter(amounts)) > 0:
        draft['max_total_cents'] = next(iter(amounts))
    elif len(amounts) > 1:
        notes.append('Multiple price limits were mentioned; clarify the maximum.')
    if '$' in text or re.search(r'\b(?:usd|dollars)\b', text):
        draft['currency'] = 'USD'
    elif re.search(r'\beur\b', text):
        draft['currency'] = 'EUR'
    if re.search(r'\b(?:nonstop|non-stop|no stops|no connections)\b', text):
        draft['max_stops'] = 0
    elif re.search(r'\bdirect\b', text):
        notes.append('Does direct mean nonstop, with no intermediate stops?')
    else:
        stops = re.search(r'\b(?:at most|max(?:imum)?|up to)\s+(\d+)\s+(?:stops?|connections?)\b', text)
        if stops:
            draft['max_stops'] = int(stops.group(1))
    if re.search(r'\bmorning\b', text):
        draft['depart_window'] = {'earliest': '06:00', 'latest': '12:00'}
        notes.append('Morning is shown as 06:00–12:00 airport-local time; review this interpretation.')
    if re.search(r'\b(?:no refund preference|refund(?:ability)? (?:does not|doesn.t) matter)\b', text):
        pass
    elif re.search(r'\b(?:non[- ]?refundable|not refundable)\b', text):
        draft['refundable_required'] = False
    elif re.search(r'\brefundable\b', text):
        draft['refundable_required'] = True
    for cabin, pattern in (
        ('premium_economy', r'\bpremium economy\b'), ('business', r'\bbusiness(?: class)?\b'),
        ('first', r'\bfirst class\b'), ('economy', r'(?<!premium )\beconomy\b'),
    ):
        if re.search(pattern, text):
            draft['cabin'] = cabin
            break
    passengers = re.search(r'\b(\d+)\s+(?:passengers?|travelers?|people)\b', text)
    if passengers:
        draft['passengers'] = int(passengers.group(1))
    return DraftRequirements.model_validate(draft).fields(), ' '.join(notes)


def extract_requirements(text: str, today: date | str | None = None) -> ExtractResult:
    """Return an unapproved draft. MOCK_LLM=1 needs no credentials or network."""
    today = date.fromisoformat(today) if isinstance(today, str) else (today or date.today())
    draft, notes = _mock_draft(text[:12000], today)
    return ExtractResult(draft_requirements=draft, questions=questions_for(draft), notes=notes, llm_fallback=True)


def explain(decision: Decision, req: ApprovedRequirements) -> ExplainResult:
    """Explain code's decision without ever changing its result or granting consent."""
    if decision.result == 'BLOCK':
        message, step = 'The authorization or merchant signature could not be verified. Choose another offer.', 'choose_another'
    elif decision.result == 'PASS':
        message, step = 'This offer matches the requirements you confirmed.', 'none'
    else:
        pending = [c for c in decision.checks if c.status in ('fail', 'missing')]
        message = ' '.join(c.message for c in pending) or 'This purchase is on hold pending review.'
        step = 'none' if any(c.check_id == 'APPROVAL' for c in pending) else 'accept_exception'
    return ExplainResult(traveler_message=message, suggested_next_step=step, llm_fallback=True)
