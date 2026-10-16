"""One selected default for interactive inference and live evaluations."""
import os
DEFAULT_PIPELINE='adaptive_fast'
PROMPT_VERSION='intent-envelope-v19-selective-review'
LEDGER_PROMPT_VERSION='intent-ledger-v6-readiness-question-contract'
REASONING_EFFORTS={'low','medium','high'}
ADAPTIVE_PIPELINES={'adaptive','adaptive_fast','ledger'}


def prompt_version_for(pipeline=None):
    """Keep the incumbent version stable when the experimental arm changes."""
    return LEDGER_PROMPT_VERSION if (pipeline or selected_pipeline()) == 'ledger' else PROMPT_VERSION

def selected_pipeline():
    return os.getenv('AI_PIPELINE_VERSION',DEFAULT_PIPELINE)


def is_adaptive_pipeline(pipeline=None):
    """Return whether a pipeline uses the model-directed question contract."""
    return (pipeline or selected_pipeline()) in ADAPTIVE_PIPELINES


def interpretation_call_count(pipeline=None, *, tool_loop=False):
    """Return the minimum calls before a turn-specific read-only tool loop.

    ``adaptive_fast`` is one model call for ordinary clarification turns.  A
    second call is reserved for a model-selected read-only observation or a
    proposed clarification contradicted by resolvable customer evidence.
    The legacy adaptive pipeline remains a two-role comparison path.
    """
    pipeline = pipeline or selected_pipeline()
    if pipeline in {'adaptive_fast', 'ledger'}:
        return 2 if tool_loop else 1
    if pipeline in {'adaptive', 'audited'}:
        return 2
    return 1


def selected_reasoning_effort():
    """Return the explicitly configured bounded reasoning level."""
    value=os.getenv('AI_REASONING_EFFORT','low').strip().lower()
    if value not in REASONING_EFFORTS:
        raise ValueError('AI_REASONING_EFFORT must be one of low, medium, or high')
    return value
