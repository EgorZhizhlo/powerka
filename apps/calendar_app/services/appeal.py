from fastapi import HTTPException, status as status_code, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.calendar_app.repositories import (
    AppealRepository, CompanyCalendarRepository
)
from infrastructure.db import async_db_session, async_db_session_begin
from models import AppealModel
from apps.calendar_app.schemas.appeals import AppealFormSchema


class AppealService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = AppealRepository(session)
        self.company_calendar_repo = CompanyCalendarRepository(session)

    async def list(
            self, company_id: int, status: str | None,
            page: int, page_size: int
    ):
        total = await self.repo.count_by_company(company_id, status=status)
        appeals = await self.repo.get_list(
            company_id=company_id,
            status=status,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return total, appeals

    async def get(self, company_id: int, appeal_id: int) -> AppealModel:
        appeal = await self.repo.get_by_id_and_company(appeal_id, company_id)
        if not appeal:
            raise HTTPException(
                status_code=status_code.HTTP_404_NOT_FOUND,
                detail="Обращение не найдено",
            )
        return appeal

    async def create(
            self, company_id: int, payload: AppealFormSchema,
            dispatcher_id: int
    ):
        company_param = await self.company_calendar_repo.get_by_company_id(
            company_id
        )

        if company_param.customer_field_required and not payload.client_full_name:
            raise HTTPException(
                status_code=status_code.HTTP_400_BAD_REQUEST,
                detail="Поле Заказчик обязательно для заполнения.",
            )

        new_appeal = AppealModel(company_id=company_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(new_appeal, field, value)

        new_appeal.dispatcher_id = dispatcher_id

        self.session.add(new_appeal)
        await self.session.flush()
        await self.session.refresh(new_appeal, attribute_names=["dispatcher"])
        return new_appeal

    async def update(
            self, company_id: int, appeal_id: int, payload: AppealFormSchema):
        appeal = await self.repo.get_by_id_and_company(appeal_id, company_id)
        if not appeal:
            raise HTTPException(
                status_code.HTTP_404_NOT_FOUND,
                "Обращение не найдено")

        company_param = await self.company_calendar_repo.get_by_company_id(
            company_id
        )
        update_data = payload.model_dump(exclude_unset=True)

        if company_param.customer_field_required:
            if "client_full_name" in update_data and not update_data["client_full_name"]:
                raise HTTPException(
                    status_code=status_code.HTTP_400_BAD_REQUEST,
                    detail="Поле 'client_full_name' не может быть пустым",
                )
            if "client_full_name" not in update_data and not appeal.client_full_name:
                raise HTTPException(
                    status_code=status_code.HTTP_400_BAD_REQUEST,
                    detail="Поле 'client_full_name' обязательно и должно быть заполнено",
                )

        for field, value in update_data.items():
            setattr(appeal, field, value)

        self.session.add(appeal)
        await self.session.flush()
        await self.session.refresh(appeal, attribute_names=["dispatcher"])
        return appeal

    async def delete(self, company_id: int, appeal_id: int):
        appeal = await self.repo.get_by_id_and_company(appeal_id, company_id)
        if not appeal:
            raise HTTPException(
                status_code=status_code.HTTP_404_NOT_FOUND,
                detail="Обращение не найдено",
            )
        await self.session.delete(appeal)


def get_read_appeal_service(
        session: AsyncSession = Depends(async_db_session)
) -> AppealService:
    return AppealService(session)


def get_action_appeal_service(
        session: AsyncSession = Depends(async_db_session_begin)
) -> AppealService:
    return AppealService(session)
