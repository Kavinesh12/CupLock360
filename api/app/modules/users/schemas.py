from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

ScopeType = Literal["branch", "warehouse", "site", "client"]


class ScopeIn(BaseModel):
    type: ScopeType
    id: int


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=60, pattern=r"^[a-zA-Z0-9._-]+$")
    full_name: str = Field(min_length=1, max_length=120)
    phone: str | None = Field(default=None, pattern=r"^[6-9]\d{9}$")
    email: EmailStr | None = None
    password: str = Field(min_length=8, max_length=128)
    roles: list[str] = Field(min_length=1)
    scopes: list[ScopeIn] = []
    approval_limit: Decimal | None = Field(default=None, ge=0)

    @field_validator("username")
    @classmethod
    def lower(cls, v: str) -> str:
        return v.lower()


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    phone: str | None = Field(default=None, pattern=r"^[6-9]\d{9}$")
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    roles: list[str] | None = None
    scopes: list[ScopeIn] | None = None
    approval_limit: Decimal | None = Field(default=None, ge=0)
    is_active: bool | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str
    phone: str | None
    email: str | None
    is_active: bool
    roles: list[str]
    scopes: list[ScopeIn]
    approval_limit: Decimal | None


class PermissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    module: str
    description: str


class RoleOut(BaseModel):
    id: int
    code: str
    name: str
    description: str | None
    is_system: bool
    permissions: list[str]
    user_count: int


class RolePermissionsUpdate(BaseModel):
    permissions: list[str]
