from typing import Any


class ApiError(Exception):
    """Expected API error rendered by the application exception handler."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


class ResourceNotFoundError(ApiError):
    def __init__(self, message: str) -> None:
        super().__init__(status_code=404, code="not_found", message=message)


class InvalidRequestError(ApiError):
    def __init__(self, message: str) -> None:
        super().__init__(status_code=422, code="validation_error", message=message)
