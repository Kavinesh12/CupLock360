from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.gst import GSTIN_RE, STATES

Phone = Field(default=None, pattern=r"^[6-9]\d{9}$")


def _upper_or_none(v: str | None) -> str | None:
    v = (v or "").strip().upper()
    return v or None


class ClientBase(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    branch_id: int
    gstin: str | None = None
    pan: str | None = Field(default=None, pattern=r"^[A-Z]{5}\d{4}[A-Z]$")
    billing_address: str | None = None
    state_code: str = "33"
    contact_name: str | None = None
    phone: str | None = Phone
    email: EmailStr | None = None
    notes: str | None = None
    is_active: bool = True

    @field_validator("gstin", mode="before")
    @classmethod
    def check_gstin(cls, v):
        v = _upper_or_none(v)
        if v and not GSTIN_RE.match(v):
            raise ValueError("Invalid GSTIN format")
        return v

    @field_validator("pan", mode="before")
    @classmethod
    def up_pan(cls, v):
        return _upper_or_none(v)

    @field_validator("state_code")
    @classmethod
    def check_state(cls, v):
        if v not in STATES:
            raise ValueError("Unknown GST state code")
        return v


class CreditFields(BaseModel):
    payment_terms_days: int = Field(default=30, ge=0, le=365)
    credit_limit: Decimal = Field(default=Decimal(0), ge=0)
    security_deposit: Decimal = Field(default=Decimal(0), ge=0)
    credit_status: Literal["pending", "approved", "hold"] = "pending"


class ClientCreate(ClientBase, CreditFields):
    pass


class ClientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    branch_id: int | None = None
    gstin: str | None = None
    pan: str | None = None
    billing_address: str | None = None
    state_code: str | None = None
    contact_name: str | None = None
    phone: str | None = Phone
    email: EmailStr | None = None
    notes: str | None = None
    is_active: bool | None = None
    payment_terms_days: int | None = Field(default=None, ge=0, le=365)
    credit_limit: Decimal | None = Field(default=None, ge=0)
    security_deposit: Decimal | None = Field(default=None, ge=0)
    credit_status: Literal["pending", "approved", "hold"] | None = None

    @field_validator("gstin", mode="before")
    @classmethod
    def check_gstin(cls, v):
        return ClientBase.check_gstin(v)

    @field_validator("pan", mode="before")
    @classmethod
    def up_pan(cls, v):
        return _upper_or_none(v)

    @field_validator("state_code")
    @classmethod
    def check_state(cls, v):
        return None if v is None else ClientBase.check_state(v)


CREDIT_FIELDS = {"payment_terms_days", "credit_limit", "security_deposit", "credit_status"}


class SiteIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    address: str | None = None
    city: str | None = None
    state_code: str = "33"
    manager_user_id: int | None = None
    contact_phone: str | None = Phone
    is_active: bool = True


class SiteOut(SiteIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    code: str
    state: str


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    branch_id: int | None = None  # defaults to the client's branch
    start_date: date | None = None
    is_active: bool = True


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    client_id: int
    code: str
    name: str
    branch_id: int
    start_date: date | None
    is_active: bool
    sites: list[SiteOut] = []


class ClientOut(ClientBase, CreditFields):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    state: str


class ClientDetail(ClientOut):
    projects: list[ProjectOut] = []


class SiteListOut(SiteOut):
    project_name: str
    client_id: int
    client_name: str
