"""Synthetic demo conversations and source traces, separate from signed authorization.

The HTTP approval handler must call record_approval after explicit traveler confirmation.
Chat text and AI responses cannot call it or change a previously confirmed snapshot.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
from uuid import uuid4

from app.foundry_client import DraftRequirements, extract_requirements, questions_for
from app.models import ApprovedRequirements


class ConversationStore:
    """In-memory demo state; stored traces are supporting evidence, not signed VI claims."""

    def __init__(self):
        self._conversations: dict[str, dict] = {}
        self._approvals: dict[str, dict] = {}

    def turn(self, conversation_id: str | None, text: str, today: date | str | None = None) -> dict:
        if not text.strip() or len(text) > 12000:
            raise ValueError('Use a nonempty message of at most 12000 characters')
        if conversation_id is None:
            conversation_id = str(uuid4())
            self._conversations[conversation_id] = {
                'conversation_id': conversation_id, 'turns': [],
                'draft_requirements': DraftRequirements().fields(), 'field_sources': {},
            }
        state = self._conversations[conversation_id]
        turn = {
            'turn_id': str(uuid4()), 'role': 'user', 'text': text,
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        extracted = extract_requirements(text, today)
        state['turns'].append(turn)
        for field, value in extracted.draft_requirements.items():
            # Defaults have no supporting words. Do not overwrite an explicit passenger count.
            if value is None or (field == 'passengers' and value == 1 and not any(word in text.lower() for word in ('traveler', 'passenger', 'people'))):
                continue
            state['draft_requirements'][field] = value
            state['field_sources'][field] = [{
                'turn_id': turn['turn_id'], 'quote': text,
                'interpretation': deepcopy(value),
            }]
        state['questions'] = questions_for(state['draft_requirements'])
        state['notes'] = extracted.notes
        state['llm_fallback'] = extracted.llm_fallback
        state['approved'] = False
        reply = ' '.join(state['questions']) or 'Review these requirements and explicitly confirm them before checkout.'
        state['turns'].append({
            'turn_id': str(uuid4()), 'role': 'assistant', 'text': reply,
            'created_at': datetime.now(timezone.utc).isoformat(),
        })
        return deepcopy(state)

    def record_approval(self, conversation_id: str, req: ApprovedRequirements) -> dict:
        """Link explicit server-recorded approval to the exact reviewed draft, once."""
        if not req.approved_by_traveler:
            raise ValueError('Explicit traveler approval is required')
        state = self._conversations[conversation_id]
        fields = {key: req.model_dump(mode='json')[key] for key in DraftRequirements.model_fields}
        reviewed = DraftRequirements.model_validate(fields).fields()
        if reviewed != state['draft_requirements']:
            raise ValueError('Approved requirements must match the reviewed draft')
        if questions_for(reviewed):
            raise ValueError('Resolve required draft fields before approval')
        if req.requirement_set_id in self._approvals:
            raise ValueError('This requirement id already has an immutable approval snapshot')
        snapshot = deepcopy(state)
        snapshot['approval'] = {
            'requirement_set_id': req.requirement_set_id,
            'approved_at': req.approved_at.isoformat(),
            'approved_requirements': req.model_dump(mode='json'),
        }
        snapshot['approved'] = True
        snapshot['trace_status'] = 'application_record_not_user_signed_transcript'
        self._approvals[req.requirement_set_id] = snapshot
        return deepcopy(snapshot)

    def trace_for_requirements(self, requirement_set_id: str) -> dict:
        """Export only the turns belonging to this confirmed snapshot, by copy."""
        return deepcopy(self._approvals[requirement_set_id])


_store = ConversationStore()


def conversation_turn(conversation_id: str | None, text: str, today: date | str | None = None) -> dict:
    return _store.turn(conversation_id, text, today)


def record_approval(conversation_id: str, req: ApprovedRequirements) -> dict:
    return _store.record_approval(conversation_id, req)


def trace_for_requirements(requirement_set_id: str) -> dict:
    return _store.trace_for_requirements(requirement_set_id)
