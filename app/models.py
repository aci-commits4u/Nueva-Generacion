"""Validated request contracts; free text never becomes authorization."""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

class IntentRequest(StrictModel):
    domain: Literal['flight','hotel','general'] = 'flight'
    message: str = Field(min_length=5,max_length=2500)
    mode: Literal['live','offline'] = 'live'

class AnswerRequest(StrictModel):
    revision: int
    fields: dict[str, Any]
    unsupported: list[str] = Field(default_factory=list,max_length=20)
    confirmation: bool

class ApprovalRequest(StrictModel):
    revision: int
    digest: str
    confirmation: bool

class CheckRequest(StrictModel):
    intent_id: str
    offer_id: str

class ExceptionRequest(StrictModel):
    check_ids: list[str] = Field(min_length=1,max_length=30)
    offer_hash: str
    confirmation: bool

class PurchaseRequest(StrictModel):
    decision_id: str
    idempotency_key: str = Field(min_length=8,max_length=100)

class DisputeRequest(StrictModel):
    purchase_id: str
    reason: str = Field(min_length=3,max_length=1000)

class ClarifyRequest(StrictModel):
    revision: int
    message: str = Field(min_length=2,max_length=1500)
