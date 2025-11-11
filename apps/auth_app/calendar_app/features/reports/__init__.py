from apps.calendar_app.features.reports.api import (
    reports_static_api_router,
    reports_dynamic_api_router,
    reports_api_router
)
from apps.calendar_app.features.reports.frontend import (
    reports_static_frontend_router
)


__all__ = [
    "reports_static_api_router",
    "reports_dynamic_api_router",
    "reports_api_router",
    "reports_static_frontend_router",
]
