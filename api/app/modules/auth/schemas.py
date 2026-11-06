import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    login: str = Field(description="Username, phone or email")
    password: str


class OtpChallengeOut(BaseModel):
    challenge_id: uuid.UUID
    channel: str
    expires_at: datetime
    sent_to: str | None = None


class VerifyOtpIn(BaseModel):
    challenge_id: uuid.UUID
    code: str = Field(min_length=4, max_length=8)


class RefreshIn(BaseModel):
    refresh_token: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class MeOut(BaseModel):
    id: int
    username: str
    full_name: str
    phone: str | None
    email: str | None
    roles: list[str]
    permissions: list[str]
    scopes: list[dict]
    approval_limit: float | None
