from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)
    nickname: str = Field(min_length=1, max_length=50)


class LoginRequest(BaseModel):
    username: str
    password: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    nickname: str
    avatar_url: str | None
    created_at: datetime


class AuthResult(BaseModel):
    token: str
    token_type: str = "bearer"
    user_info: UserRead
