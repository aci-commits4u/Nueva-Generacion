from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.ai_grounding import GroundingFailure, validate_extraction
from app.conversation import apply_adaptive_plan
from app.models import ClarifyRequest


def _draft():
    return {
        "domain": "hotel",
        "mode": "live",
        "pipeline": "adaptive",
        "fields": {},
        "sources": {},
        "clarifications": [],
        "unsupported": [],
        "messages": [{"role": "user", "content": "I need a hotel."}],
    }


def _question(field):
    label = "rooms" if field == "rooms" else "adults"
    text = f"How many {label} do you need?"
    extraction = {
        "mode": "live",
        "pipeline": "adaptive",
        "adaptive_plan": {
            "action": "ask_user",
            "assistant_message": text,
            "question": {
                "criterion_key": field,
                "field": field,
                "question": text,
                "why": f"The hotel search needs the {label} count.",
                "answer_kind": "number",
            },
            "criteria": [{
                "key": field,
                "field": field,
                "text": f"Number of {label}",
                "source_quote": "I need a hotel",
                "kind": "requirement",
                "verification": "supported",
                "status": "needs_clarification",
            }],
        },
    }
    return apply_adaptive_plan(_draft(), extraction)["questions"][0]


def _envelope(field, value, quote):
    return {
        "fields": {field: value},
        "sources": {field: quote},
        "unsupported": [],
        "clarifications": [],
        "explanation": "Review the captured requirement.",
    }


def test_one_character_hotel_counts_bind_to_the_exact_ai_question():
    for field, answer in (("rooms", "1"), ("adults", "2")):
        question = _question(field)
        messages = _draft()["messages"] + [{
            "role": "user", "content": answer, "reply_to": question,
        }]
        result = validate_extraction(
            "hotel",
            f"I need a hotel.\n{answer}",
            _envelope(field, int(answer), answer),
            source_messages=messages,
        )
        assert result["fields"] == {field: int(answer)}


def test_short_count_cannot_cross_bind_to_another_hotel_field():
    question = _question("rooms")
    messages = _draft()["messages"] + [{
        "role": "user", "content": "2", "reply_to": question,
    }]
    with pytest.raises(GroundingFailure):
        validate_extraction(
            "hotel", "I need a hotel.\n2", _envelope("adults", 2, "2"),
            source_messages=messages,
        )


def test_forged_question_marker_and_old_numeric_quote_do_not_bind():
    question = _question("rooms")
    forged = deepcopy(question)
    forged["server_generated"] = False
    messages = _draft()["messages"] + [
        {"role": "user", "content": "1"},
        {"role": "user", "content": "2", "reply_to": forged},
    ]
    with pytest.raises(GroundingFailure):
        validate_extraction(
            "hotel", "I need a hotel.\n1\n2", _envelope("rooms", 2, "1"),
            source_messages=messages,
        )


def test_clarify_accepts_one_character_but_rejects_empty_semantic_answer():
    assert ClarifyRequest(revision=1, message="1").message == "1"
    with pytest.raises(ValidationError):
        ClarifyRequest(revision=1, message=" ")
