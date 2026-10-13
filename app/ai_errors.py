"""Safe, actionable AI errors. Provider payloads and credentials stay private."""
from uuid import uuid4


class AIServiceError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 503,
                 retryable: bool = False, retry_after_seconds: int | None = None,
                 stage: str | None = None):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds
        self.stage = stage
        self.request_id = uuid4().hex[:12]

    def public(self) -> dict:
        return {'code': self.code, 'message': str(self), 'retryable': self.retryable,
                'retry_after_seconds': self.retry_after_seconds,
                'request_id': self.request_id}
