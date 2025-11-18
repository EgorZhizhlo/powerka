from fastapi import APIRouter

from apps.webhook_app.features.appeals import appeals_webhooks_router


webhook_router = APIRouter(prefix='/webhook')
webhook_router.include_router(
    appeals_webhooks_router
)
