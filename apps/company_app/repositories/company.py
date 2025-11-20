from typing import Optional
from fastapi import Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import CompanyModel

from infrastructure.db import async_db_session_begin, async_db_session

from core.config import settings


class CompanyRepository:
    def __init__(self, session: AsyncSession, company_id: int):
        self._session = session
        self._company_id = company_id

    async def get_company_for_context(self) -> Optional[dict]:
        stmt = (
            select(
                CompanyModel.id,
                CompanyModel.name,
                CompanyModel.image,
                CompanyModel.auto_teams,
                CompanyModel.is_active,
            )
            .where(CompanyModel.id == self._company_id)
        )

        res = await self._session.execute(stmt)
        return res.mappings().one_or_none()


async def read_company_repository(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    session: AsyncSession = Depends(async_db_session),
) -> CompanyRepository:
    return CompanyRepository(session=session, company_id=company_id)


async def action_company_repository(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    session: AsyncSession = Depends(async_db_session_begin),
) -> CompanyRepository:
    return CompanyRepository(session=session, company_id=company_id)
