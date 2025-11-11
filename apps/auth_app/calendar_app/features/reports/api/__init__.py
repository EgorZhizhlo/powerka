from apps.calendar_app.features.reports.api.dynamic.router import (
    reports_dynamic_api_router
)
from apps.calendar_app.features.reports.api.static.router import (
    reports_static_api_router
)
from apps.calendar_app.features.reports.api.base.router import (
    reports_api_router
)


__all__ = [
    "reports_static_api_router",
    "reports_dynamic_api_router",
    "reports_api_router",
]
