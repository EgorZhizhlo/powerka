import math
from fastapi import (
    APIRouter, HTTPException, status as status_code,
    Body, Query, Depends
)

from core.config import settings

from access_control import (
    JwtData,
    dispatcher2_exception,
    active_dispatcher2_exception
)

from models.enums import map_appeal_status_to_label

from apps.calendar_app.schemas.appeals import (
    AppealsPaginated, AppealSchema, AppealFormSchema
)
from apps.calendar_app.services import (
    AppealService,
    get_read_appeal_service,
    get_action_appeal_service
)


appeals_api_router = APIRouter(prefix="/api/appeals")


@appeals_api_router.get("/", response_model=AppealsPaginated)
async def api_appeals_list(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    appeal_status: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    employee_data: JwtData = Depends(dispatcher2_exception),
    appeal_service: AppealService = Depends(get_read_appeal_service),
):
    if appeal_status and appeal_status not in map_appeal_status_to_label:
        raise HTTPException(
            status_code=status_code.HTTP_400_BAD_REQUEST,
            detail=f"Фильтр статуса должен быть одним из: {
                ', '.join(map_appeal_status_to_label.keys())}",
        )

    total, appeals = await appeal_service.list(
        company_id, appeal_status or None, page, page_size)

    total_pages = math.ceil(total / page_size) if total else 0
    return AppealsPaginated(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        items=appeals,
    )


@appeals_api_router.get(
        "/appeal",
        response_model=AppealSchema
)
async def api_appeal_get(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    appeal_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data=Depends(dispatcher2_exception),
    appeal_service: AppealService = Depends(get_read_appeal_service),
):
    return await appeal_service.get(company_id, appeal_id)


@appeals_api_router.post(
        "/appeal/create", response_model=AppealSchema,
        status_code=status_code.HTTP_201_CREATED
)
async def api_appeal_create(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    payload: AppealFormSchema = Body(...),
    employee_data: JwtData = Depends(active_dispatcher2_exception),
    appeal_service: AppealService = Depends(get_action_appeal_service),
):
    return await appeal_service.create(company_id, payload, employee_data.id)


@appeals_api_router.put(
        "/appeal/update",
        response_model=AppealSchema
)
async def api_appeal_update(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    appeal_id: int = Query(..., ge=1, le=settings.max_int),
    payload: AppealFormSchema = Body(...),
    employee_data: JwtData = Depends(active_dispatcher2_exception),
    appeal_service: AppealService = Depends(get_action_appeal_service),
):
    return await appeal_service.update(company_id, appeal_id, payload)


@appeals_api_router.delete(
        "/appeal/delete",
        status_code=status_code.HTTP_204_NO_CONTENT
)
async def api_appeal_delete(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    appeal_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data=Depends(active_dispatcher2_exception),
    appeal_service: AppealService = Depends(get_action_appeal_service),
):
    await appeal_service.delete(company_id, appeal_id)
