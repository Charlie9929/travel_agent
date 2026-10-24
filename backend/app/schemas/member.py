from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MemberInvite(BaseModel):
    user_id: int
    role: str = Field(default="editor", pattern=r"^(editor|viewer)$")


class MemberRoleUpdate(BaseModel):
    role: str = Field(pattern=r"^(editor|viewer)$")


class MemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trip_id: int
    user_id: int
    role: str
    joined_at: datetime


class JoinTripRequest(BaseModel):
    share_code: str = Field(min_length=1, max_length=32)


class ShareCodeRequest(BaseModel):
    expires_in_hours: int = Field(default=72, ge=1, le=720)


class ShareCodeResult(BaseModel):
    share_code: str
    expires_at: datetime
