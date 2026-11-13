from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LobbyMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    reply_to_id: int | None = Field(default=None, ge=1)
    ask_agent: bool = False


class LobbyMessageRead(BaseModel):
    id: int
    trip_id: int
    sender_id: int | None
    sender_nickname: str | None = None
    sender_avatar_url: str | None = None
    kind: str
    content: str
    visibility: str
    reply_to_id: int | None
    structured_data: dict[str, Any]
    created_at: datetime


class LobbyMessagePage(BaseModel):
    items: list[LobbyMessageRead]
    unread_count: int
    next_after_id: int | None


class MarkLobbyReadRequest(BaseModel):
    last_read_message_id: int = Field(ge=1)


class AgentConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trip_id: int
    user_id: int
    title: str
    created_at: datetime
    updated_at: datetime


class AgentChatMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class AgentChatMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    role: str
    content: str
    status: str
    error_code: str | None
    structured_data: dict[str, Any]
    created_at: datetime


class AgentChatSendResult(BaseModel):
    user_message: AgentChatMessageRead
    agent_message: AgentChatMessageRead


class RequirementUpsert(BaseModel):
    content: dict[str, Any]
    status: Literal["pending", "completed"] = "completed"


class RequirementShareRequest(BaseModel):
    summary: str = Field(min_length=1, max_length=1000)


class RequirementRead(BaseModel):
    id: int
    trip_id: int
    user_id: int
    nickname: str
    avatar_url: str | None
    content: dict[str, Any] | None
    status: str
    filled_by: int | None
    filled_by_nickname: str | None
    shared_summary: str | None
    shared_at: datetime | None
    can_view_private: bool
    updated_at: datetime


class MemoryCreate(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=5000)
    visibility: Literal["private", "shared"] = "private"
    authorized_trip_ids: list[int] = Field(default_factory=list)


class MemoryUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    content: str | None = Field(default=None, min_length=1, max_length=5000)
    visibility: Literal["private", "shared"] | None = None
    authorized_trip_ids: list[int] | None = None


class MemoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    content: str
    visibility: str
    authorized_trip_ids: list[int]
    created_at: datetime
    updated_at: datetime


class HighlightCreate(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    activity_id: int | None = Field(default=None, ge=1)
    content: str | None = Field(default=None, max_length=5000)
    image_url: str | None = Field(default=None, max_length=500)
    occurred_at: datetime | None = None


class HighlightUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    activity_id: int | None = Field(default=None, ge=1)
    content: str | None = Field(default=None, max_length=5000)
    image_url: str | None = Field(default=None, max_length=500)
    occurred_at: datetime | None = None


class HighlightMediaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_url: str
    mime_type: str
    size_bytes: int
    sort_order: int
    created_at: datetime


class HighlightRead(BaseModel):

    id: int
    trip_id: int
    activity_id: int | None
    created_by: int
    title: str
    content: str | None
    image_url: str | None
    occurred_at: datetime | None
    created_at: datetime
    updated_at: datetime
    images: list[HighlightMediaRead] = Field(default_factory=list)


class HighlightImageReorder(BaseModel):
    image_ids: list[int] = Field(min_length=1, max_length=3)


class ExpenseSplitInput(BaseModel):
    user_id: int
    ratio: Decimal | None = Field(default=None, gt=0, le=1)
    should_pay: Decimal | None = Field(default=None, ge=0)


class ExpenseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    amount: Decimal = Field(gt=0)
    payer_id: int
    activity_id: int | None = None
    split_type: Literal["equal", "ratio"] = "equal"
    participant_ids: list[int] = Field(default_factory=list)
    splits: list[ExpenseSplitInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_split_input(self) -> "ExpenseCreate":
        if self.split_type == "equal" and not self.participant_ids:
            raise ValueError("equal 分摊必须提供 participant_ids")
        if self.split_type == "ratio" and not self.splits:
            raise ValueError("ratio 分摊必须提供 splits")
        return self


class ExpenseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    amount: Decimal | None = Field(default=None, gt=0)
    payer_id: int | None = None
    activity_id: int | None = None
    split_type: Literal["equal", "ratio"] | None = None
    participant_ids: list[int] | None = None
    splits: list[ExpenseSplitInput] | None = None


class ExpenseSplitRead(BaseModel):
    user_id: int
    nickname: str
    ratio: Decimal
    should_pay: Decimal


class ExpenseRead(BaseModel):
    id: int
    trip_id: int
    activity_id: int | None
    payer_id: int
    payer_nickname: str
    title: str
    amount: Decimal
    split_type: str
    is_settled: bool
    settled_at: datetime | None
    settled_by: int | None
    splits: list[ExpenseSplitRead]
    created_at: datetime
    updated_at: datetime


class ExpenseSettlementRequest(BaseModel):
    expense_ids: list[int] = Field(default_factory=list)
    settled: bool = True


class SettlementTransfer(BaseModel):
    from_user_id: int
    from_nickname: str
    to_user_id: int
    to_nickname: str
    amount: Decimal


class UserSearchRead(BaseModel):
    id: int
    username: str
    nickname: str
    avatar_url: str | None
    is_member: bool
    can_invite: bool


class ProfileUpdate(BaseModel):
    nickname: str | None = Field(default=None, min_length=1, max_length=50)
    avatar_url: str | None = Field(default=None, max_length=255)


class UserSettingsUpdate(BaseModel):
    agent_preferences: dict[str, Any] | None = None
    memory_enabled: bool | None = None


class UserSettingsRead(BaseModel):
    agent_preferences: dict[str, Any]
    memory_enabled: bool
