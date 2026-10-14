"""One selected default for interactive inference and live evaluations."""
import os
DEFAULT_PIPELINE='adaptive'
PROMPT_VERSION='intent-envelope-v8-route-choices'
REASONING_EFFORTS={'low','medium','high'}

def selected_pipeline():
    return os.getenv('AI_PIPELINE_VERSION',DEFAULT_PIPELINE)


def selected_reasoning_effort():
    """Return the explicitly configured bounded reasoning level."""
    value=os.getenv('AI_REASONING_EFFORT','low').strip().lower()
    if value not in REASONING_EFFORTS:
        raise ValueError('AI_REASONING_EFFORT must be one of low, medium, or high')
    return value
