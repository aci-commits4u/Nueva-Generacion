"""Present the semantic ledger without reinterpreting it in legacy repair code.

The model chooses question meaning and words. This bridge only binds that
question to the stored customer-answer contract and rejects settled targets.
"""
from copy import deepcopy

from app.profile_registry import get_profile


def attach_ledger_plan(draft, extraction):
    from app.conversation import _adaptive_question, user_text

    result = deepcopy(draft)
    ledger = extraction.get('intent_ledger')
    if not isinstance(ledger, dict) or ledger.get('revision') != result['revision']:
        raise ValueError('The intent ledger does not match the saved revision.')
    result.update(
        pipeline='ledger',
        intent_ledger=deepcopy(ledger),
        ledger_transition=deepcopy(extraction.get('ledger_transition')),
        fields=deepcopy(extraction['fields']),
        sources=deepcopy(extraction['sources']),
        unsupported=deepcopy(extraction['unsupported']),
        clarifications=deepcopy(extraction.get('clarifications', [])),
        review_deferred=False,
    )
    result.pop('review_warning', None)
    criteria = deepcopy(extraction.get('criteria', []))
    profile = get_profile(result['domain'])
    known_keys = {record.get('key') for record in criteria}
    # Missing required facts can be question targets, but are not customer
    # requirements or invented customer quotations.
    for field, spec in profile['fields'].items():
        if spec.get('required') and result['fields'].get(field) is None and field not in known_keys:
            criteria.append({
                'key': field, 'field': field, 'text': spec['label'],
                'source_quote': None, 'kind': 'ambiguity',
                'verification': 'supported', 'status': 'needs_clarification',
            })
    plan = deepcopy(extraction.get('adaptive_plan') or {})
    raw_question = plan.get('question')
    question = _adaptive_question(
        result['domain'], raw_question, criteria,
        fields=result['fields'], source_text=user_text(result.get('messages', [])),
    )
    settled = False
    if question is not None:
        field = question.get('field')
        key = question['criterion_key']
        record = next((item for item in criteria if item.get('key') == key), None)
        pending = {item.get('field') for item in result['clarifications']}
        settled = bool(
            (record and record.get('status') in {'captured', 'declined', 'no_preference'})
            or (field in result['fields'] and field not in pending)
        )
    suppressed = raw_question is not None and (question is None or settled)
    if suppressed:
        question = None
        plan['assistant_message'] = ''
        plan['suppressed_question'] = {'reason': 'settled_or_invalid_ledger_target'}
    if question is not None:
        plan['action'] = 'ask_user'
    else:
        ready = (
            not result['unsupported'] and not result['clarifications']
            and all(result['fields'].get(field) is not None
                    for field, spec in profile['fields'].items() if spec.get('required'))
        )
        plan['action'] = 'ready_for_review' if ready else 'review_required'
    plan['question'] = deepcopy(question)
    plan['offer_observations'] = []
    result.update(
        questions=[question] if question else [], adaptive_plan=plan,
        criteria=criteria, generic_criteria=deepcopy(criteria), agent_tools=[],
    )
    result.pop('read_only_tool_log', None)
    result.pop('fact_context', None)
    draft.clear()
    draft.update(result)
    return draft
