from fastapi import APIRouter

from app.api.routes.agent_audit import router as agent_audit_router
from app.api.routes.business_tasks import router as business_tasks_router
from app.api.routes.confirmation_drafts import router as confirmation_drafts_router
from app.api.routes.family import router as family_router
from app.api.routes.knowledge import router as knowledge_router
from app.api.routes.medication import router as medication_router
from app.api.routes.pharmacy import router as pharmacy_router
from app.api.routes.system import router as system_router

api_router = APIRouter()
api_router.include_router(system_router, tags=["system"])
api_router.include_router(family_router, tags=["family"])
api_router.include_router(medication_router, tags=["medication"])
api_router.include_router(pharmacy_router, tags=["pharmacy"])
api_router.include_router(agent_audit_router, tags=["agent-audit"])
api_router.include_router(business_tasks_router, tags=["business-tasks"])
api_router.include_router(knowledge_router, tags=["knowledge"])
api_router.include_router(confirmation_drafts_router, tags=["confirmation-drafts"])
