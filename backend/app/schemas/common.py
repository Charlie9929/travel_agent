from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: str = "SUCCESS"
    data: T
    msg: str = "success"


class ErrorResponse(BaseModel):
    code: str
    data: Any | None = None
    msg: str
