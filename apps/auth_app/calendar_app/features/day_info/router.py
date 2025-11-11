from fastapi import APIRouter, Query, Depends
from datetime import date as date_

from core.config import settings

from access_control import (
    JwtData,
    dispatcher2_exception,
    active_dispatcher2_exception
)

from apps.calendar_app.services import (
    DayInfoService,
    get_read_day_info_service,
    get_action_day_info_service
)

from apps.calendar_app.schemas.day_info import DayInfoSchema


day_info_api_router = APIRouter(prefix="/api/day-info")


@day_info_api_router.get("/")
async def get_day_info(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    date_info: date_ = Query(...),
    employee_data: JwtData = Depends(dispatcher2_exception),
    day_info_service: DayInfoService = Depends(get_read_day_info_service),
):
    return await day_info_service.get_day_info(company_id, date_info)


@day_info_api_router.post("/upsert", response_model=DayInfoSchema)
async def upsert_day_info(
    payload: DayInfoSchema,
    company_id: int = Query(..., ge=1, le=settings.max_int),
    date_info: date_ = Query(...),
    employee_data: JwtData = Depends(active_dispatcher2_exception),
    day_info_service: DayInfoService = Depends(get_action_day_info_service),
):
    return await day_info_service.upsert_day_info(
        company_id, date_info, payload.day_info)


@day_info_api_router.get("/period")
async def calendar_day_info(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    date_for: date_ = Query(...),
    date_to: date_ = Query(...),
    employee_data: JwtData = Depends(dispatcher2_exception),
    day_info_service: DayInfoService = Depends(get_read_day_info_service),
):
    return await day_info_service.get_calendar_day_info(
        company_id, date_for, date_to)
