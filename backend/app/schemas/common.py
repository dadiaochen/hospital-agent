from typing import Any

from pydantic import BaseModel, ConfigDict


class ApiSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        protected_namespaces=(),
    )


class ApiErrorDetail(ApiSchema):
    code: str
    message: str
    details: list[dict[str, Any]] | None = None


class ApiErrorResponse(ApiSchema):
    error: ApiErrorDetail
