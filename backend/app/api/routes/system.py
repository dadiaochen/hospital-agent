from fastapi import APIRouter

from app.schemas.system import SystemStatus

router = APIRouter()


@router.get("/health", response_model=SystemStatus)
async def api_health() -> SystemStatus:
    return SystemStatus(status="ok", phase="phase-1-skeleton")

