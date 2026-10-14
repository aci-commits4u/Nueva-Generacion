"""Validated request contracts; free text never becomes authorization."""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


def validate_time_zone(value):
    if type(value) is not str or not value or len(value)>80:
        raise ValueError('time_zone must be a valid IANA time-zone name')
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError('time_zone must be a valid IANA time-zone name')
    return value


class IntentRequest(StrictModel):
    domain: Literal['flight','hotel','general'] = 'flight'
    message: str = Field(min_length=5,max_length=2500)
    mode: Literal['live','offline'] = 'live'
    time_zone: str = 'UTC'

    @field_validator('time_zone')
    @classmethod
    def valid_time_zone(cls,value):
        return validate_time_zone(value)


class ProfileRefreshRequest(StrictModel):
    revision: int
    time_zone: str

    @field_validator('time_zone')
    @classmethod
    def valid_time_zone(cls,value):
        return validate_time_zone(value)

class AnswerRequest(StrictModel):
    revision: int
    fields: dict[str, Any]
    unsupported: list[str] = Field(default_factory=list,max_length=20)
    removed_unsupported: list[str] = Field(default_factory=list,max_length=20)
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
