from apps.calendar_app.features.appeals import (
    appeals_api_router,
    appeals_frontend_router
)

from apps.calendar_app.features.day_info import (
    day_info_api_router
)

from apps.calendar_app.features.orders_calendar import (
    orders_calendar_api_router,
    orders_calendar_frontend_router
)

from apps.calendar_app.features.orders_planning import (
    orders_planning_api_router,
    orders_planning_frontend_router
)

from apps.calendar_app.features.orders_search import (
    orders_search_api_router,
    orders_search_frontend_router
)

from apps.calendar_app.features.orders_without_date import (
    orders_without_date_api_router, orders_without_date_frontend_router
)

from apps.calendar_app.features.reports import (
    reports_static_api_router,
    reports_dynamic_api_router,
    reports_api_router,
    reports_static_frontend_router
)


__all__ = [
    # appeals
    "appeals_api_router",
    "appeals_frontend_router",

    # day_info
    "day_info_api_router",

    # orders_calendar
    "orders_calendar_api_router",
    "orders_calendar_frontend_router",

    # orders_planning
    "orders_planning_api_router",
    "orders_planning_frontend_router",

    # orders_search
    "orders_search_api_router",
    "orders_search_frontend_router",

    # orders_without_date
    "orders_without_date_api_router",
    "orders_without_date_frontend_router",

    # reports
    "reports_static_api_router",
    "reports_dynamic_api_router",
    "reports_api_router",
    "reports_static_frontend_router",
]
