"""Profile-driven clarification without AI consent or guessed preferences."""
from app.profile_registry import get_profile,digest
from copy import deepcopy
import json
import re


# The adaptive planner is deliberately carried beside the reviewed profile
# draft.  These values are presentation and audit metadata; they never enter
# the signed requirements object or the deterministic rules engine.
_ADAPTIVE_BINDING = 'intent-judge-ai-question-v1'
_ADAPTIVE_ACTIONS = {
    'ask_user', 'inspect_offers', 'retrieve_policy',
    'ready_for_review', 'review_required',
}
_ADAPTIVE_ANSWER_KINDS = {
    'single', 'multi', 'date_choice', 'text', 'number', 'boolean',
}
_ADAPTIVE_CRITERION_KINDS = {'requirement', 'preference', 'ambiguity'}


def _adaptive_question_contract(domain, question):
    """Return the stable semantic contract used by a server-owned AI question.

    The digest is an integrity check for the stored reply binding.  It is not
    a user credential: the API chooses the stored question object and never
    accepts a client-supplied ``reply_to`` object.  Keeping the contract here
    also lets grounding validate short answers without trusting question text
    supplied by a customer.
    """
    return {
        'domain': domain,
        'criterion_key': question.get('criterion_key'),
        'field': question.get('field'),
        'question': question.get('question'),
        'response_type': question.get('response_type'),
        'answer_kind': question.get('answer_kind'),
        'answer_semantics': question.get('answer_semantics'),
        'options': deepcopy(question.get('options') or []),
    }


def adaptive_question_id(domain, question):
    """Derive a stable identifier from the question's semantic contract."""
    return 'q_' + digest(_adaptive_question_contract(domain, question))[:16]


def is_trusted_adaptive_question(question, domain=None):
    """Check a question binding produced by :func:`apply_adaptive_plan`.

    This intentionally has a narrow shape.  A matching string in ``question``
    is not enough to bind a customer answer; the server marker, id, and
    contract digest must all agree.  ``domain`` is optional for callers that
    only need structural validation, but grounding supplies it when available.
    """
    if not isinstance(question, dict):
        return False
    if question.get('origin') != 'ai' or question.get('server_generated') is not True:
        return False
    if question.get('binding') != _ADAPTIVE_BINDING:
        return False
    if not isinstance(question.get('id'), str) or question.get('id') != question.get('question_id'):
        return False
    if domain is None:
        domain = question.get('domain')
    if not isinstance(domain, str):
        return False
    expected_id = adaptive_question_id(domain, question)
    if question.get('id') != expected_id:
        return False
    expected_contract = digest(_adaptive_question_contract(domain, question))
    return question.get('contract_digest') == expected_contract


def user_text(messages):
    return '\n'.join(m['content'] for m in messages)


def context(messages):
    turns=[]
    for message in messages:
        if message.get('reply_to'):
            reply=message['reply_to']
            # Interface text is context only.  Keeping the stable question
            # contract here lets the model understand a short answer without
            # treating the interface wording as customer evidence.
            turns.append({'role':'interface_question',
                          'question_id':reply.get('question_id',reply.get('id')),
                          'field':reply.get('field'),
                          'response_type':reply.get('response_type'),
                          'answer_kind':reply.get('answer_kind'),
                          'answer_semantics':reply.get('answer_semantics'),
                          'criterion_key':reply.get('criterion_key'),
                          'origin':reply.get('origin'),
                          'binding':reply.get('binding'),
                          'contract_digest':reply.get('contract_digest'),
                          'options':reply.get('options',[]),
                          'why':reply.get('why'),
                          'content':reply.get('question')})
        turns.append({'role':'customer','content':message['content']})
    return json.dumps(turns,ensure_ascii=True)


def merge_unsupported(*groups):
    values=list(dict.fromkeys(x for group in groups for x in group))
    if len(values)>20 or sum(len(x.encode()) for x in values)>6000:
        raise ValueError('Too many flagged conditions for a reviewable demo request. Your previous draft is preserved; use review or split the request.')
    return values


def declined_preferences(domain,messages):
    """Route past explicit declines without turning them into approval.

    These source-linked choices only suppress redundant optional questions.
    Every omitted field must still be explicitly reviewed before signing.
    Required fields are never skipped by a no-preference statement.
    """
    profile=get_profile(domain)
    terms={
        'nonstop':r'non[- ]?stop', 'refundable':r'refundable|refundability|cancellation',
        'breakfast':r'breakfast', 'accessible':r'accessible|accessibility',
        'departure_window':r'departure time|departure window|takeoff time',
        'max_duration_minutes':r'trip duration|journey duration|flight duration',
        'max_connections':r'connections?|layovers?', 'cabin':r'cabin',
        'trip_type':r'trip type', 'rooms':r'rooms?',
    }
    declined={}
    for message in messages or []:
        if message.get('role') not in {'user','customer'}:continue
        text=message.get('content','')
        reply=message.get('reply_to') or {}
        field=reply.get('field');spec=profile['fields'].get(field,{})
        if (spec and not spec.get('required') and reply.get('question')==spec['question']
                and re.fullmatch(r'(?:no(?: thanks)?|no preference)[.!?, ]*',text.strip(),re.I)):
            declined[field]=text
        # Adaptive questions are generated at runtime, so their wording is
        # intentionally not compared with the profile's static question.  A
        # short No/No-preference reply is trusted only when the server-owned
        # question contract validates and its target field is optional.  The
        # same reply without the contract remains ordinary customer text.
        if (field and spec and not spec.get('required')
                and is_trusted_adaptive_question(reply, domain=domain)
                and re.fullmatch(r'(?:no(?: thanks)?|no preference)[.!?, ]*', text.strip(), re.I)):
            declined[field]=text
        for clause in re.split(r'[.!?;\n]|\bbut\b|\bhowever\b|\band\s+(?=I\s+(?:require|need|want)\b)',text,flags=re.I):
            declines=re.search(r'\bno preference\b|\bno (?:need|requirement)\b|\b(?:do not|don[’\']t)\s+(?:require|need|care)\b|\bnot (?:required|needed)\b',clause,re.I)
            for key,term in terms.items():
                explicit_no_requirement=re.search(r'\bno\s+(?:'+term+r')\s+requirement\b',clause,re.I)
                if ((declines or explicit_no_requirement) and key in profile['fields'] and not profile['fields'][key].get('required')
                        and re.search(r'\b(?:'+term+r')\b',clause,re.I)):
                    declined[key]=clause.strip()
    return declined


_OPTIONAL_DECLINE_TERMS = {
    'nonstop': r'non[- ]?stop|direct',
    'refundable': r'refundable|refundability|refund|cancellation|cancel(?:lation)?',
    'breakfast': r'breakfast|morning meal',
    'accessible': r'accessible|accessibility',
    'departure_window': r'departure time|departure window|takeoff time',
    'max_duration_minutes': r'trip duration|journey duration|flight duration',
    'max_connections': r'connections?|layovers?',
    'cabin': r'cabin|economy|business|first',
    'trip_type': r'trip type|one[- ]way|round trip',
    'rooms': r'rooms?',
    'adults': r'adults?|guests?',
}


def _latest_optional_decline_sources(domain, messages):
    """Return only the latest explicit optional declines by field.

    ``declined_preferences`` is the source parser for this decision.  This
    second pass prevents a stale historical decline from clearing a value that
    a later customer turn explicitly requires.  It also keeps the exact
    customer clause returned by the source parser as the field provenance.
    """
    profile = get_profile(domain)
    parsed = declined_preferences(domain, messages)
    if not parsed:
        return {}
    decline_pattern = re.compile(
        r'\b(?:no\s+preference|no\s+(?:need|requirement)|'
        r'(?:do\s+not|don[’\']t)\s+(?:require|need|care)|'
        r'not\s+(?:required|needed))\b', re.I,
    )
    positive_pattern = re.compile(
        r'\b(?:actually\s+)?(?:require|need|want|must|prefer|'
        r'required|essential|important|include|including)\b|\b(?:yes|yeah)\b',
        re.I,
    )
    latest = {}
    for index, message in enumerate(messages or []):
        if not isinstance(message, dict) or message.get('role') not in {'user', 'customer'}:
            continue
        text = str(message.get('content') or '')
        reply = message.get('reply_to')
        for field, quote in parsed.items():
            spec = profile.get('fields', {}).get(field)
            if not spec or spec.get('required'):
                continue
            term = _OPTIONAL_DECLINE_TERMS.get(field)
            field_mentioned = bool(term and re.search(r'\b(?:' + term + r')\b', text, re.I))
            trusted_reply = (
                isinstance(reply, dict)
                and reply.get('field') == field
                and is_trusted_adaptive_question(reply, domain=domain)
            )
            direct_no_preference = trusted_reply and bool(re.fullmatch(
                r'(?:no(?: thanks)?|no preference)[.!?, ]*', text.strip(), re.I,
            ))
            static_no_preference = (
                isinstance(reply, dict)
                and reply.get('field') == field
                and isinstance(spec.get('question'), str)
                and reply.get('question') == spec.get('question')
                and bool(re.fullmatch(
                    r'(?:no(?: thanks)?|no preference)[.!?, ]*', text.strip(), re.I,
                ))
            )
            direct_no_preference = direct_no_preference or static_no_preference
            if not field_mentioned and not direct_no_preference:
                continue
            decline_matches = list(decline_pattern.finditer(text))
            positive_matches = list(positive_pattern.finditer(text))
            if direct_no_preference:
                decline_matches.append(re.match(r'.*', text, re.S))
            last_decline = max((match.end() for match in decline_matches), default=-1)
            last_positive = max((match.end() for match in positive_matches), default=-1)
            if last_decline < 0 and last_positive < 0:
                # Mentioning an optional field without a preference marker is
                # not enough to erase a previous choice.
                continue
            if last_decline >= last_positive:
                latest[field] = (index, quote)
            else:
                latest[field] = (index, None)
    return {field: parsed[field] for field, (_index, quote) in latest.items()
            if quote is not None}


def _response_type(spec):
    """Map a reviewed profile field to the shape of its customer answer."""
    field_type=spec.get('type') if isinstance(spec,dict) else None
    return {
        'strings':'multi',
        'date_choice':'date_choice',
        'window':'time_range',
    }.get(field_type,'single')


def _question_id(domain,field,spec):
    """Return a stable id for one profile question and answer contract."""
    question=spec.get('question','') if isinstance(spec,dict) else ''
    response_type=_response_type(spec)
    return f"q_{digest({'domain':domain,'field':field,'question':question,'response_type':response_type})[:16]}"


def _question(domain,field,spec,*,required=False):
    response_type=_response_type(spec)
    choices=spec.get('choices') or spec.get('enum') or spec.get('values') or []
    if not isinstance(choices,list):
        choices=[]
    question_id=_question_id(domain,field,spec)
    return {
        'id':question_id,
        'question_id':question_id,
        'field':field,
        'question':spec['question'],
        'required':bool(required),
        'response_type':response_type,
        'allow_multiple':response_type=='multi',
        'options':deepcopy(choices),
    }


def _bounded_adaptive_text(value, limit=800):
    if not isinstance(value, str):
        return ''
    return value.strip()[:limit]


def _normalise_adaptive_criteria(raw, *, source_text=None):
    """Keep generic planner criteria as review context only.

    ``field`` is intentionally nullable.  A generic condition may be useful
    for a follow-up question while remaining outside the domain profile.  The
    condition is never copied into ``draft['fields']`` and therefore cannot
    affect a PASS decision.
    """
    if not isinstance(raw, list):
        return []
    criteria = []
    seen = {}
    for item in raw[:40]:
        if not isinstance(item, dict):
            continue
        key = item.get('key') or item.get('criterion_key') or item.get('field')
        text = _bounded_adaptive_text(item.get('text') or item.get('requirement'), 500)
        if not isinstance(key, str) or not key.strip() or not text:
            continue
        key = key.strip()[:120]
        kind = item.get('kind', 'requirement')
        if kind not in _ADAPTIVE_CRITERION_KINDS:
            kind = 'requirement'
        field = item.get('field') if isinstance(item.get('field'), str) else None
        verification = item.get('verification')
        if verification not in {'supported', 'unsupported'}:
            verification = 'supported' if field else 'unsupported'
        status = item.get('status')
        if status not in {'captured', 'needs_clarification', 'declined', 'unsupported'}:
            status = 'captured' if verification == 'supported' and field else 'needs_clarification'
        quote = item.get('source_quote')
        if not isinstance(quote, str) or not quote.strip():
            quote = None
        else:
            quote = quote.strip()[:500]
        why = _bounded_adaptive_text(item.get('why'), 500)
        # The planner has already been source-grounded upstream.  This helper
        # does not elevate an unverified quote: retain it only as provenance.
        normalized = {
            'key': key,
            'field': field,
            'text': text,
            'source_quote': quote,
            'kind': kind,
            'verification': verification,
            'status': status,
            'why': why,
        }
        if key in seen:
            # Later reviewer output can resolve or revise a prior criterion;
            # omission is handled by the caller's prior+latest merge.
            criteria[seen[key]] = normalized
        else:
            seen[key] = len(criteria)
            criteria.append(normalized)
    return criteria


def _adaptive_options(raw):
    options = []
    if not isinstance(raw, list):
        return options
    for item in raw[:12]:
        if isinstance(item, str):
            label = item.strip()[:160]
            if label:
                options.append({'label': label, 'value': label})
        elif isinstance(item, dict):
            label = _bounded_adaptive_text(item.get('label'), 160)
            value = _bounded_adaptive_text(item.get('value') or label, 160)
            if label and value:
                options.append({'label': label, 'value': value})
    return options


def _adaptive_question(domain, raw, criteria, *, allow_offer_context=False,
                       fields=None):
    """Create a server-owned question contract from planner metadata.

    Boolean questions need an explicit requirement semantic.  A question like
    “Is nonstop essential or merely preferred?” is a useful conversation
    prompt, but a bare Yes must not silently become ``nonstop=True``.
    """
    if not isinstance(raw, dict):
        return None
    question = _bounded_adaptive_text(raw.get('question') or raw.get('text'), 500)
    why = _bounded_adaptive_text(raw.get('why'), 500)
    criterion_key = raw.get('criterion_key') or raw.get('key') or raw.get('field')
    if not isinstance(criterion_key, str) or not criterion_key.strip() or not question or not why:
        return None
    criterion_key = criterion_key.strip()[:120]
    criterion = next((item for item in criteria if item.get('key') == criterion_key), None)
    if criterion is None and isinstance(fields, dict):
        criterion = next((item for item in criteria if item.get('field') == criterion_key), None)
    if criterion is None:
        return None
    answer_kind = raw.get('answer_kind') or raw.get('response_type') or 'text'
    if answer_kind not in _ADAPTIVE_ANSWER_KINDS:
        return None
    field = raw.get('field') if isinstance(raw.get('field'), str) else None
    if field is None and criterion.get('field'):
        field = criterion['field']
    if field is not None:
        profile = get_profile(domain)
        if field not in profile.get('fields', {}):
            # A generic question may refer to a null field; it may not smuggle
            # a made-up typed profile field into the signed review.
            field = None
    # Optional profile fields are not interrogated merely because they are
    # absent.  A source-less optional question is allowed only after the
    # planner has supplied real merchant/offer context that makes it material.
    if not criterion.get('source_quote') and field is not None:
        spec = get_profile(domain).get('fields', {}).get(field, {})
        if not spec.get('required') and not allow_offer_context:
            return None
    options = _adaptive_options(raw.get('options'))
    answer_semantics = raw.get('answer_semantics')
    if answer_semantics not in {'requirement_boolean', 'preference_boolean', None}:
        answer_semantics = None
    if answer_kind == 'boolean':
        # Only the first semantic is allowed to bind Yes/No to a true
        # requirement.  The wording check prevents an ambiguous model question
        # from being treated as an authoritative boolean contract.
        if answer_semantics == 'requirement_boolean':
            if not re.search(r'\b(?:require|requires|required|need|needs|needed|must|necessary|essential)\b', question, re.I):
                answer_semantics = None
            if re.search(r'\b(?:prefer|preferred|preference|or\s+just)\b', question, re.I):
                answer_semantics = None
        elif answer_semantics == 'preference_boolean':
            # A preference may be declined, but a short Yes must not silently
            # create a hard requirement.
            if not re.search(r'\b(?:care|prefer|preference|important|matter)\b', question, re.I):
                answer_semantics = None
        else:
            answer_semantics = None
        if answer_semantics is None:
            # Keep an otherwise useful question, but downgrade it to a full
            # answer contract.  This makes a bare Yes non-authoritative.
            answer_kind = 'single' if options else 'text'
    response_type = answer_kind
    contract = {
        'domain': domain,
        'criterion_key': criterion_key,
        'field': field,
        'question': question,
        'response_type': response_type,
        'answer_kind': answer_kind,
        'answer_semantics': answer_semantics,
        'options': options,
    }
    question_id = 'q_' + digest(contract)[:16]
    return {
        'id': question_id,
        'question_id': question_id,
        'domain': domain,
        'criterion_key': criterion_key,
        'field': field,
        'question': question,
        'required': bool(raw.get('required', False)),
        'response_type': response_type,
        'answer_kind': answer_kind,
        'answer_semantics': answer_semantics,
        'allow_multiple': answer_kind == 'multi',
        'options': options,
        'why': why,
        'origin': 'ai',
        'server_generated': True,
        'binding': _ADAPTIVE_BINDING,
        'contract_digest': digest(contract),
    }


def _adaptive_question_answered(question, draft, criteria=None):
    """Return true once the customer has answered this exact question."""
    qid = question.get('question_id')
    key = question.get('criterion_key')
    messages = draft.get('messages', []) or []
    answered_index = None
    answered_keys = []
    for index, message in enumerate(messages):
        reply = message.get('reply_to') if isinstance(message, dict) else None
        if not isinstance(reply, dict) or not is_trusted_adaptive_question(
                reply, domain=draft.get('domain')):
            continue
        if reply.get('question_id') == qid:
            answered_index = index
        if key and reply.get('criterion_key') == key:
            answered_keys.append((index, reply.get('question_id')))
    criterion = next((item for item in (criteria or [])
                      if isinstance(item, dict) and item.get('key') == key), None)
    criterion_status = criterion.get('status') if criterion else None
    # A new question for the same generic criterion is allowed only when the
    # latest planner state explicitly says the answer remains ambiguous. This
    # lets “I don't know” lead to a useful follow-up while preventing every
    # wording change from repeating an already answered question.
    if answered_keys and not any(item[1] == qid for item in answered_keys):
        if criterion_status == 'needs_clarification' and question.get('why'):
            return False
        return True
    if answered_index is not None:
        field = question.get('field')
        terms = {
            'nonstop': r'non[- ]?stop|direct|connection|layover',
            'refundable': r'refund|cancel',
            'breakfast': r'breakfast',
            'accessible': r'accessib',
            'departure_window': r'depart|takeoff|morning|afternoon|evening',
            'cabin': r'cabin|economy|business|first',
        }
        reopened = any(
            index > answered_index
            and isinstance(message, dict)
            and message.get('role') in {'user', 'customer'}
            and field
            and re.search(terms.get(field, re.escape(field)), message.get('content', ''), re.I)
            for index, message in enumerate(messages)
        )
        if not reopened:
            return True
    field = question.get('field')
    fields = draft.get('fields') if isinstance(draft.get('fields'), dict) else {}
    clarifications = draft.get('clarifications') or []
    pending_fields = {item.get('field') for item in clarifications if isinstance(item, dict)}
    if (field and field in fields and fields.get(field) is not None
            and field not in pending_fields):
        return True
    # An explicit No/no-preference on an AI question is a recorded decline for
    # optional criteria.  Do not keep asking unless a later customer turn
    # explicitly reopens that topic.
    domain = draft.get('domain')
    if (field and isinstance(domain, str)
            and field in declined_preferences(domain, draft.get('messages', []))):
        messages = draft.get('messages', []) or []
        decline_quote = _latest_optional_decline_sources(domain, messages).get(field)
        decline_indexes = []
        for index, message in enumerate(messages):
            reply = message.get('reply_to') if isinstance(message, dict) else None
            content = str(message.get('content', '')) if isinstance(message, dict) else ''
            source_decline = (
                isinstance(decline_quote, str)
                and decline_quote.casefold() in content.casefold()
            )
            bound_decline = (
                isinstance(reply, dict) and reply.get('field') == field
                and is_trusted_adaptive_question(reply, domain=domain)
                and re.fullmatch(r'(?:no(?: thanks)?|no preference)[.!?, ]*',
                                 content.strip(), re.I)
            )
            if source_decline or bound_decline:
                decline_indexes.append(index)
        last_decline = max(decline_indexes, default=-1)
        terms = {
            'nonstop': r'non[- ]?stop|direct|connection|layover',
            'refundable': r'refund|cancel',
            'breakfast': r'breakfast',
            'accessible': r'accessib',
            'departure_window': r'depart|takeoff|morning|afternoon|evening',
            'cabin': r'cabin|economy|business|first',
        }
        reopened = any(
            index > last_decline
            and isinstance(message, dict)
            and message.get('role') in {'user', 'customer'}
            and re.search(terms.get(field, re.escape(field)), message.get('content', ''), re.I)
            for index, message in enumerate(messages)
        )
        if not reopened:
            return True
    return False


def _generic_answer_is_ambiguous(text):
    """Classify only obvious non-answers; the model still reviews meaning."""
    if not isinstance(text, str) or not text.strip():
        return True
    return bool(re.fullmatch(
        r"\s*(?:idk|i\s+don['’]?t\s+know|(?:i['’]?m|i\s+am)\s+not\s+sure|not\s+sure|unclear|maybe|it\s+depends|"
        r"no\s+idea|unsure)[.!?, ]*\s*",
        text,
        re.I,
    ))


def _generic_answers_from_messages(domain, messages):
    """Read exact answers only from server-owned adaptive reply bindings."""
    answers = {}
    for index, message in enumerate(messages or []):
        if not isinstance(message, dict) or message.get('role') not in {'user', 'customer'}:
            continue
        reply = message.get('reply_to')
        if not isinstance(reply, dict) or reply.get('field') is not None:
            continue
        if not reply.get('criterion_key') or not is_trusted_adaptive_question(reply, domain=domain):
            continue
        content = message.get('content')
        if not isinstance(content, str):
            continue
        answers[reply['criterion_key']] = {
            'answer_quote': content,
            'answer_timestamp': message.get('timestamp'),
            'answer_question_id': reply.get('question_id'),
            'answer_message_index': index,
            'answer_status': 'needs_clarification' if _generic_answer_is_ambiguous(content) else 'captured',
            'answer_provenance': 'server_owned_reply_binding',
        }
    return answers


def _attach_generic_answers(domain, criteria, messages):
    """Attach authoritative answer records to generic criteria.

    A model cannot claim that a customer answered a generic criterion.  The
    exact answer quote and timestamp come from the stored conversation's
    server-owned question binding.  A latest model criterion may explicitly
    keep the answer ambiguous when it supplies a new reason; otherwise a
    clear answer resolves the repeat-question state, while unsupported
    verification still remains a purchase HOLD.
    """
    answers = _generic_answers_from_messages(domain, messages)
    result = []
    for item in criteria:
        value = deepcopy(item)
        answer = answers.get(value.get('key'))
        if answer:
            value.update(answer)
            explicit_ambiguity = (
                value.get('status') == 'needs_clarification'
                and bool(value.get('why'))
            )
            if not explicit_ambiguity:
                value['status'] = answer['answer_status']
        result.append(value)
    return result


def _apply_typed_optional_declines(result, criteria):
    """Compile explicit optional no-preference clauses into review state.

    This is a server-owned projection of a customer's exact sentence.  The
    language model cannot create a ``None`` field or a declined criterion;
    it only supplies the adaptive plan around this state.  ``None`` remains a
    review value, so the final structured review still has to acknowledge it.
    """
    if result.get('approved'):
        return criteria
    domain = result.get('domain')
    if not isinstance(domain, str):
        return criteria
    profile = get_profile(domain)
    messages = result.get('messages', []) or []
    declined = _latest_optional_decline_sources(domain, messages)
    if not declined:
        return criteria
    fields = result.get('fields') if isinstance(result.get('fields'), dict) else {}
    sources = result.get('sources') if isinstance(result.get('sources'), dict) else {}
    result['fields'] = fields
    result['sources'] = sources
    clarifications = result.get('clarifications') or []
    # A decline only resolves the matching typed clarification.  Generic
    # unsupported flags and unrelated typed clarifications remain reviewable.
    result['clarifications'] = [
        item for item in clarifications
        if not (isinstance(item, dict) and item.get('field') in declined)
    ]
    by_key = {item.get('key'): index for index, item in enumerate(criteria)
              if isinstance(item, dict) and item.get('key')}
    for field, quote in declined.items():
        spec = profile.get('fields', {}).get(field)
        if not spec or spec.get('required'):
            continue
        fields[field] = None
        sources[field] = quote
        record = {
            'key': field,
            'field': field,
            'text': spec.get('label') or field,
            'source_quote': quote,
            'kind': 'preference',
            'verification': 'supported',
            'status': 'declined',
        }
        existing_index = by_key.get(field)
        if existing_index is None:
            by_key[field] = len(criteria)
            criteria.append(record)
        else:
            # Preserve any additional planner metadata, while making the
            # customer-owned source, typed verification, and status explicit.
            criteria[existing_index].update(record)
    return criteria


def _adaptive_ready(domain, draft, criteria):
    profile = get_profile(domain)
    fields = draft.get('fields') if isinstance(draft.get('fields'), dict) else {}
    if any(spec.get('required') and fields.get(field) is None
           for field, spec in profile.get('fields', {}).items()):
        return False
    if draft.get('clarifications') or draft.get('unsupported'):
        return False
    if any(item.get('status') in {'needs_clarification', 'unsupported'}
           or item.get('verification') == 'unsupported'
           for item in criteria):
        return False
    return True


def apply_adaptive_plan(draft, extraction):
    """Attach a normalized adaptive plan to a draft and select its AI question.

    This is the bridge used by intake/clarification handlers after the latest
    grounded state has been merged.  In live adaptive mode it never falls back
    to profile questions: no valid AI question means no question.  Offline and
    legacy pipelines keep the existing deterministic profile question list.
    """
    result = deepcopy(draft)
    extraction = extraction if isinstance(extraction, dict) else {}
    mode = extraction.get('mode', result.get('mode', 'offline'))
    pipeline = extraction.get('pipeline', result.get('pipeline', 'offline'))
    adaptive = mode == 'live' and pipeline == 'adaptive'
    raw_plan = extraction.get('adaptive_plan') or extraction.get('planner') or extraction.get('plan')
    if raw_plan is None and any(key in extraction for key in ('action', 'question', 'criteria')):
        raw_plan = extraction
    if not isinstance(raw_plan, dict):
        raw_plan = {}
    criteria_raw = (extraction.get('generic_criteria') or extraction.get('criteria')
                    or raw_plan.get('criteria') or [])
    # A reviewer may omit a previously discovered generic criterion while
    # re-reading the latest turn. Preserve the earlier source-backed record;
    # omission is not customer correction. New records with the same key win.
    prior_criteria = result.get('generic_criteria') or result.get('criteria') or []
    criteria = _normalise_adaptive_criteria([*prior_criteria, *criteria_raw])
    if adaptive:
        # Required routing facts may be absent because the customer has not
        # supplied them yet. The model is allowed to ask for those facts, but
        # the synthetic criterion has no source quote and never becomes a
        # typed requirement until the customer answers it.
        fields = result.get('fields') if isinstance(result.get('fields'), dict) else {}
        profile = get_profile(result.get('domain'))
        existing = {item.get('key') for item in criteria}
        for field, spec in profile.get('fields', {}).items():
            if spec.get('required') and fields.get(field) is None and field not in existing:
                criteria.append({
                    'key': field,
                    'field': field,
                    'text': spec.get('label') or field,
                    'source_quote': None,
                    'kind': 'ambiguity',
                    'verification': 'supported',
                    'status': 'needs_clarification',
                })
        criteria = _attach_generic_answers(
            result.get('domain'), criteria, result.get('messages', []),
        )
        # Explicit customer no-preference clauses are compiled after the
        # merged draft is available.  This fills typed optional fields with a
        # reviewable ``None`` and suppresses their matching question without
        # treating silence or model output as consent.
        criteria = _apply_typed_optional_declines(result, criteria)
        # Unknown customer conditions must remain visible to deterministic
        # review.  A nullable field or explicit unsupported verification is
        # advisory context only until it has a real profile operator; keep its
        # source quote as a flagged condition so purchase cannot ignore it.
        flagged = [
            item.get('source_quote') for item in criteria
            if isinstance(item.get('source_quote'), str)
            and (item.get('field') is None or item.get('verification') == 'unsupported')
            and item.get('source_quote').strip()
        ]
        current_flags = list(result.get('unsupported') or [])
        for quote in flagged:
            if quote in current_flags:
                continue
            try:
                current_flags = merge_unsupported(current_flags, [quote])
            except ValueError:
                # Never truncate a condition merely to fit the storage cap.
                # The caller must reject the turn before persisting the draft;
                # otherwise a removed last condition could weaken the purchase
                # gate while the UI still displays an apparently valid plan.
                raise ValueError(
                    'Too many flagged generic conditions to review safely. '
                    'The previous draft is preserved; split the request.'
                )
        result['unsupported'] = current_flags
    raw_question = raw_plan.get('question')
    observations = raw_plan.get('offer_observations')
    question = (_adaptive_question(
        result.get('domain'), raw_question, criteria,
        allow_offer_context=isinstance(observations, list) and bool(observations),
        fields=result.get('fields'),
    ) if adaptive else None)
    action = raw_plan.get('action') if raw_plan.get('action') in _ADAPTIVE_ACTIONS else 'review_required'
    if adaptive:
        if question is not None and not _adaptive_question_answered(question, result, criteria):
            result['questions'] = [question]
            if action != 'ask_user':
                action = 'ask_user'
        else:
            result['questions'] = []
            if action == 'ask_user':
                action = 'review_required' if not _adaptive_ready(result.get('domain'), result, criteria) else 'ready_for_review'
        if action == 'ready_for_review' and not _adaptive_ready(result.get('domain'), result, criteria):
            action = 'review_required'
        if action == 'inspect_offers':
            # A planner must not claim it inspected commerce without enough
            # grounded routing facts.  Tool execution remains read-only.
            required = {
                'flight': {'origin_airports', 'destination_airports', 'departure_date'},
                'hotel': {'city', 'checkin_date', 'checkout_date'},
                'general': set(),
            }.get(result.get('domain'), set())
            fields = result.get('fields') if isinstance(result.get('fields'), dict) else {}
            if not required.issubset(fields):
                action = 'review_required'
    else:
        # Keep old callers and offline mode on the tested deterministic path.
        result['questions'] = questions(
            result.get('domain'), result.get('fields', {}),
            result.get('clarifications'), result.get('messages'),
        )
        # Do not let a stale planner snapshot switch an offline/legacy draft
        # into the adaptive UI.  Offline remains an explicit deterministic
        # emergency path with the existing profile question contract.
        for key in ('adaptive_plan', 'generic_criteria', 'criteria', 'agent_tools',
                    'read_only_tool_log', 'fact_context'):
            result.pop(key, None)
        if isinstance(draft, dict):
            draft.clear()
            draft.update(result)
            return draft
        return result
    tools = extraction.get('agent_tools') or extraction.get('adaptive_tools') or raw_plan.get('agent_tools') or raw_plan.get('tools') or []
    if isinstance(tools, dict):
        tools = [tools]
    result['adaptive_plan'] = {
        'action': action,
        'assistant_message': _bounded_adaptive_text(raw_plan.get('assistant_message'), 1000),
        'question': deepcopy(question),
        'offer_observations': deepcopy(raw_plan.get('offer_observations') or [])[:20] if isinstance(raw_plan.get('offer_observations'), list) else [],
    }
    result['generic_criteria'] = criteria
    result['criteria'] = deepcopy(criteria)
    result['agent_tools'] = deepcopy(tools)[:20] if isinstance(tools, list) else []
    # Keep the actual read-only merchant/tool trace beside the planner summary
    # so the UI and evidence layer can distinguish facts returned by a tool
    # from model-written observations. It has no approval authority.
    tool_log = extraction.get('read_only_tool_log')
    if tool_log is None:
        tool_log = extraction.get('tool_result')
    if tool_log is not None:
        result['read_only_tool_log'] = deepcopy(tool_log)
        result['fact_context'] = deepcopy(tool_log)
    # Explicitly preserve extraction flags.  Generic criteria are explanatory
    # context and must never silently remove unsupported conditions.  Mutate
    # the caller's draft as well as returning it: the API handlers historically
    # use stateful ``refresh`` helpers and call this bridge for its side effect.
    if isinstance(draft, dict):
        draft.clear()
        draft.update(result)
        return draft
    return result


def questions(domain,fields,clarifications=None,messages=None):
    """Plan only required gaps and source-backed ambiguities.

    Optional profile fields are choices for review, not an interrogation list.
    They become conversational questions only when the customer actually
    mentioned an ambiguous supported condition.  This prevents a nonstop
    requirement from triggering a redundant maximum-connections question.
    """
    profile=get_profile(domain)
    declined=declined_preferences(domain,messages)
    planned=[]
    for key,spec in profile['fields'].items():
        if spec.get('required') and fields.get(key) is None:
            planned.append(_question(domain,key,spec,required=True))
    planned_fields={item['field'] for item in planned}
    mentioned={}
    for item in clarifications or []:
        if not isinstance(item,dict):
            continue
        field=item.get('field')
        if (field not in profile['fields'] or fields.get(field) is not None
                or not item.get('source_quote')):
            continue
        if field in declined:
            continue
        mentioned.setdefault(field,item)
    for key,spec in profile['fields'].items():
        if key not in mentioned or key in planned_fields:
            continue
        # Nonstop is a stricter form of the connections rule. Asking for both
        # makes the conversation appear contradictory and invites a model to
        # manufacture a second preference.
        if key=='max_connections' and fields.get('nonstop') is True:
            continue
        planned.append(_question(domain,key,spec,required=bool(spec.get('required'))))
    return planned


_TEXT_EQUIVALENTS=str.maketrans({
    '\u2010':'-', '\u2011':'-', '\u2012':'-', '\u2013':'-', '\u2014':'-',
    '\u2015':'-', '\u2212':'-', '\u00a0':' ', '\u202f':' ',
})


def _quote_in_latest_turn(quote,latest_turn):
    if not isinstance(quote,str) or not isinstance(latest_turn,str):
        return False
    return quote.translate(_TEXT_EQUIVALENTS).casefold() in latest_turn.translate(_TEXT_EQUIVALENTS).casefold()


_CLARIFICATION_FIELD_HINTS={
    'max_total_cents':('budget','price','cost','total','under','up to','maximum','$','usd','dollar','flexible'),
    'origin_airports':('airport','depart','departure','from','newark','jfk','laguardia','lga','ewr'),
    'destination_airports':('airport','arrive','arrival','to','orlando','miami','tampa','mco','mia','tpa','fll','florida'),
    'departure_date':('date','travel','depart','departure','today','tomorrow','week','jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'),
    'nonstop':('nonstop','direct','connection','layover','stop'),
    'max_connections':('connection','layover','stop'),
    'departure_window':('time','morning','afternoon','evening','night','am','pm',':'),
    'max_duration_minutes':('duration','hour','minute','long'),
    'cabin':('cabin','economy','business','first','premium'),
    'refundable':('refund','refundable','cancellation'),
    'trip_type':('one-way','one way','outbound','round trip'),
    'city':('city','hotel','new york','orlando','miami','tampa','boston'),
    'checkin_date':('check-in','checkin','date','today','tomorrow','jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'),
    'checkout_date':('check-out','checkout','date','today','tomorrow','jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'),
    'breakfast':('breakfast','morning meal'),
    'accessible':('accessible','accessibility'),
    'rooms':('room','rooms'),
    'adults':('adult','adults','guest','guests'),
}


def _clarification_field_supported(domain,field,item,latest_turn,messages):
    """Bound a latest-turn clarification to the field it actually discusses."""
    quote=item.get('source_quote') if isinstance(item,dict) else None
    if field not in get_profile(domain).get('fields',{}) or not _quote_in_latest_turn(quote,latest_turn):
        return False
    # Grounding may provide a richer semantic-unit map as it evolves. Keep
    # this call optional so conversation state remains usable with older code.
    try:
        from app.ai_grounding import clarification_field_supported
    except ImportError:
        clarification_field_supported=None
    if clarification_field_supported is not None:
        try:
            if clarification_field_supported(
                field=field,quote=quote,domain=domain,source_messages=messages,
            ):
                return True
        except TypeError:
            pass
    latest_reply={}
    for message in reversed(messages or []):
        if message.get('content')==latest_turn and message.get('reply_to'):
            latest_reply=message['reply_to']
            break
    if latest_reply.get('field')==field:
        return True
    lowered=quote.translate(_TEXT_EQUIVALENTS).casefold()
    return any(token in lowered for token in _CLARIFICATION_FIELD_HINTS.get(field,()))


def merge_revision_state(domain,current,proposed,latest_turn,messages):
    """Reconcile a model proposal into the previous unapproved draft.

    The provider may omit a previously captured field while re-reading the
    whole conversation.  Omission therefore retains state.  A changed value
    is accepted only when its exact source quotation occurs in the latest
    customer turn; this keeps old model text from overwriting a newer choice.
    A latest source-backed clarification can reopen an existing value as a
    pending review item, while the change record keeps the old value and
    provenance for auditability.
    Explicit optional no-preference language clears a field for this draft,
    but remains unapproved until the structured review.
    """
    previous_fields=deepcopy(current.get('fields',{}))
    previous_sources=deepcopy(current.get('sources',{}))
    proposed_fields=proposed.get('fields',{}) if isinstance(proposed,dict) else {}
    proposed_sources=proposed.get('sources',{}) if isinstance(proposed,dict) else {}
    proposed_clarifications=proposed.get('clarifications',[]) if isinstance(proposed,dict) else []
    fields=deepcopy(previous_fields)
    sources=deepcopy(previous_sources)
    changes=[]
    all_declines=declined_preferences(domain,messages)
    latest_declines=declined_preferences(domain,[messages[-1]] if messages else [])
    latest_reopens={}
    for item in proposed_clarifications or []:
        field=item.get('field') if isinstance(item,dict) else None
        if (field in fields and field not in latest_declines
                and _clarification_field_supported(domain,field,item,latest_turn,messages)):
            latest_reopens[field]=deepcopy(item)
    for key,value in proposed_fields.items():
        quote=proposed_sources.get(key)
        if key not in fields:
            # A full-history provider response can recover a criterion that
            # the previous proposal missed. The original source remains
            # usable unless the customer explicitly declined that field in a
            # prior turn; a latest-turn quote always wins and supports a new
            # capture even after an earlier decline.
            if (not _quote_in_latest_turn(quote,latest_turn)
                    and key in all_declines):
                continue
            fields[key]=deepcopy(value)
            if isinstance(quote,str):
                sources[key]=deepcopy(quote)
            changes.append({'field':key,'kind':'captured','new_value':deepcopy(value),'new_source_quote':quote})
            continue
        if fields[key]==value:
            # Keep the original provenance unless the model supplied a newer
            # exact quote for the same value.
            if _quote_in_latest_turn(quote,latest_turn):
                sources[key]=deepcopy(quote)
            continue
        if _quote_in_latest_turn(quote,latest_turn):
            changes.append({'field':key,'kind':'corrected','old_value':deepcopy(fields[key]),
                            'new_value':deepcopy(value),'old_source_quote':sources.get(key),
                            'new_source_quote':quote})
            fields[key]=deepcopy(value)
            if isinstance(quote,str):
                sources[key]=deepcopy(quote)
    for key in latest_declines:
        if key in fields and not get_profile(domain)['fields'].get(key,{}).get('required'):
            changes.append({'field':key,'kind':'declined','old_value':deepcopy(fields[key]),
                            'old_source_quote':sources.get(key)})
            fields.pop(key,None)
            sources.pop(key,None)
    for key,item in latest_reopens.items():
        if key not in fields:
            continue
        changes.append({'field':key,'kind':'clarified','old_value':deepcopy(fields[key]),
                        'old_source_quote':sources.get(key),
                        'new_clarification':deepcopy(item)})
        fields.pop(key,None)
        sources.pop(key,None)
    clarifications={}
    for item in current.get('clarifications',[]) or []:
        if isinstance(item,dict) and item.get('field') not in fields:
            clarifications[item['field']]=deepcopy(item)
    for item in proposed_clarifications or []:
        if (isinstance(item,dict)
                and (item.get('field') not in fields or item.get('field') in latest_reopens)):
            clarifications[item.get('field')]=deepcopy(item)
    for key in latest_declines:
        clarifications.pop(key,None)
    return {
        'fields':fields,
        'sources':sources,
        'clarifications':list(clarifications.values()),
        'changes':changes,
    }


def provenance(extraction,revision,messages=None):
    adaptive_plan = extraction.get('adaptive_plan') or extraction.get('planner') or extraction.get('plan')
    if adaptive_plan is None and any(key in extraction for key in ('action', 'question', 'criteria')):
        adaptive_plan = extraction
    return {
        'revision': revision,
        'mode': extraction['mode'],
        'pipeline': extraction.get('pipeline', 'offline'),
        'model': extraction.get('model'),
        'trace': deepcopy(extraction.get('trace', [])),
        'fields': deepcopy(extraction['fields']),
        'sources': deepcopy(extraction['sources']),
        'unsupported': deepcopy(extraction['unsupported']),
        'clarifications': deepcopy(extraction.get('clarifications', [])),
        'guidance': extraction['explanation'],
        # These are immutable per-run context snapshots.  They are never
        # merged into the approved fields, even when a later run changes the
        # question or merchant tool result.
        'adaptive_plan': deepcopy(adaptive_plan) if isinstance(adaptive_plan, dict) else None,
        'agent_tools': deepcopy(extraction.get('agent_tools') or extraction.get('adaptive_tools') or []),
        'generic_criteria': deepcopy(
            extraction.get('generic_criteria') or extraction.get('criteria')
            or (adaptive_plan.get('criteria', []) if isinstance(adaptive_plan, dict) else [])
        ),
        'read_only_tool_log': deepcopy(
            extraction.get('read_only_tool_log') or extraction.get('tool_result')
        ),
        'fact_context': deepcopy(extraction.get('fact_context')),
        'conversation_digest': digest(messages or []),
        'source_message_indexes': {
            k: [i for i, m in enumerate(messages or [])
                if isinstance(quote, str) and quote.casefold() in m.get('content', '').casefold()]
            for k, quote in extraction['sources'].items()
        },
        'clarification_source_message_indexes': {
            item['field']: [i for i, m in enumerate(messages or [])
                            if isinstance(item.get('source_quote'), str)
                            and item['source_quote'].casefold() in m.get('content', '').casefold()]
            for item in extraction.get('clarifications', [])
            if isinstance(item, dict) and isinstance(item.get('field'), str)
        },
    }
