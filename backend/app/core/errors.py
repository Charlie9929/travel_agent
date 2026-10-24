from typing import Any


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        detail: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = detail


class NotFoundError(AppError):
    def __init__(self, message: str = "资源不存在", detail: Any | None = None) -> None:
        super().__init__("NOT_FOUND", message, status_code=404, detail=detail)


class ForbiddenError(AppError):
    def __init__(self, message: str = "没有权限执行该操作") -> None:
        super().__init__("FORBIDDEN", message, status_code=403)


class ConflictError(AppError):
    def __init__(self, message: str, detail: Any | None = None) -> None:
        super().__init__("VERSION_CONFLICT", message, status_code=409, detail=detail)
