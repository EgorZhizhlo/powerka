from fastapi import APIRouter

from apps.calendar_app.features import (
    appeals_api_router,
    appeals_frontend_router,

    day_info_api_router,

    orders_calendar_api_router,
    orders_calendar_frontend_router,

    orders_planning_api_router,
    orders_planning_frontend_router,

    orders_search_api_router,
    orders_search_frontend_router,

    orders_without_date_api_router,
    orders_without_date_frontend_router,

    reports_static_api_router,
    reports_dynamic_api_router,
    reports_api_router,
    reports_static_frontend_router
)


calendar_router = APIRouter(prefix="/calendar")

# API
calendar_router.include_router(
    appeals_api_router
)  # /api/appeals
calendar_router.include_router(
    day_info_api_router
)  # /api/day-info
calendar_router.include_router(
    orders_calendar_api_router
)  # /api/orders/calendar
calendar_router.include_router(
    orders_planning_api_router
)  # /api/orders/planning
calendar_router.include_router(
    orders_search_api_router
)  # /api/orders/search
calendar_router.include_router(
    orders_without_date_api_router
)  # /api/orders/without-date
calendar_router.include_router(
    reports_api_router
)  # /api/reports
calendar_router.include_router(
    reports_static_api_router
)  # /api/reports/static
calendar_router.include_router(
    reports_dynamic_api_router
)  # /api/reports/dynamic

# FRONTEND
calendar_router.include_router(
    appeals_frontend_router
)  # /appeals
calendar_router.include_router(
    orders_calendar_frontend_router
)  # /
calendar_router.include_router(
    orders_planning_frontend_router
)  # /planning
calendar_router.include_router(
    orders_search_frontend_router
)  # /search
calendar_router.include_router(
    orders_without_date_frontend_router
)  # /without-date
calendar_router.include_router(
    reports_static_frontend_router
)  # /reports/static
