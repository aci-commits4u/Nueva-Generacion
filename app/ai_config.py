"""One selected default for interactive inference and live evaluations."""
import os
DEFAULT_PIPELINE='audited'
def selected_pipeline():
    return os.getenv('AI_PIPELINE_VERSION',DEFAULT_PIPELINE)
