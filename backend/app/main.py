from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import settings
from app.core.exceptions import ApiError
from app.schemas.common import ApiErrorDetail, ApiErrorResponse


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Family health operations Agent API. This service does not diagnose, prescribe, or modify prescriptions.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(ApiError)
    async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
        response = ApiErrorResponse(
            error=ApiErrorDetail(
                code=exc.code,
                message=exc.message,
                details=exc.details,
            )
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=response.model_dump(mode="json"),
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        _: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        response = ApiErrorResponse(
            error=ApiErrorDetail(
                code="validation_error",
                message="request validation failed",
                details=jsonable_encoder(exc.errors()),
            )
        )
        return JSONResponse(status_code=422, content=response.model_dump(mode="json"))

    @app.get("/", tags=["system"])
    async def root() -> dict[str, str]:
        return {
            "service": settings.app_name,
            "version": settings.app_version,
            "status": "ok",
            "phase": "phase-1-skeleton",
        }

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(api_router, prefix="/api")
    return app


app = create_app()
