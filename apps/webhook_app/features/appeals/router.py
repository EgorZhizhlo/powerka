from fastapi import APIRouter, Depends, Body, Query

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models import AppealModel, CompanyModel

from infrastructure.db.session import async_db_session_begin

from core.exceptions.api import NotFoundError

from apps.webhook_app.schemas.appeals import AppealWebHookForm


appeals_webhooks_router = APIRouter(
    prefix='/appeals'
)


@appeals_webhooks_router.post(
    "/create"
)
async def create_appeal_by_webhook(
    company_name: str = Query(...),
    form: AppealWebHookForm = Body(...),
    session: AsyncSession = Depends(async_db_session_begin),
):
    company_result = await session.execute(
        select(CompanyModel.id).where(
            func.lower(CompanyModel.name) == company_name.strip().lower()
        )
    )
    company_id = company_result.scalar_one_or_none()
    if not company_id:
        raise NotFoundError(
            detail="Компания не найдена!"
        )

    new_appeal = AppealModel(
        client_full_name=form.client_full_name,
        address=form.address,
        phone_number=form.phone_number,
        additional_info=form.additional_info,
        company_id=company_id
    )
    session.add(new_appeal)
    await session.flush()

    return {"appeal_id": new_appeal.id, "message": "Обращение создано"}
