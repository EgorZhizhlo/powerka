from fastapi import Depends, Query
from sqlalchemy import select, delete, exists
from sqlalchemy.orm import selectinload, joinedload, load_only, contains_eager
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.db import async_db_session_begin, async_db_session
from models import (
    VerificationEntryModel,
    MetrologInfoModel,
    EquipmentModel,
    EquipmentInfoModel,
    CompanyModel,
    ReasonModel
)
from core.config import settings

from access_control import admin_director, auditor_verifier


class MetrologInfoRepository:
    def __init__(self, session: AsyncSession, company_id: int):
        self._session = session
        self._company_id = company_id

    async def check_exist_metrolog_info(
        self,
        verification_entry_id: int,
    ) -> bool:
        stmt = select(
            exists().where(
                MetrologInfoModel.company_id == self._company_id,
                MetrologInfoModel.verification_id == verification_entry_id,
            )
        )

        res = await self._session.execute(stmt)
        return res.scalar()

    async def get_for_create(
        self, verification_entry_id: int,
        employee_id: int | None, status
    ) -> VerificationEntryModel | None:
        stmt = (
            select(VerificationEntryModel)
            .options(
                load_only(
                    VerificationEntryModel.id,
                    VerificationEntryModel.company_id,
                    VerificationEntryModel.verifier_id,
                    VerificationEntryModel.employee_id,
                    VerificationEntryModel.reason_id,
                    VerificationEntryModel.verification_result,
                    VerificationEntryModel.verification_date,
                ),
                joinedload(VerificationEntryModel.reason)
                .load_only(
                    ReasonModel.full_name,
                    ReasonModel.type,
                ),
                selectinload(VerificationEntryModel.equipments)
                .load_only(
                    EquipmentModel.id,
                    EquipmentModel.name,
                    EquipmentModel.factory_number,
                )
                .joinedload(EquipmentModel.equipment_info)
                .load_only(
                    EquipmentInfoModel.id,
                    EquipmentInfoModel.type,
                    EquipmentInfoModel.date_to,
                ),
            )
            .where(
                VerificationEntryModel.id == verification_entry_id,
                VerificationEntryModel.company_id == self._company_id
            )
            .with_for_update(of=VerificationEntryModel)
        )

        if status in auditor_verifier:
            stmt = stmt.where(
                VerificationEntryModel.company.has(
                    CompanyModel.verification_date_block <
                    VerificationEntryModel.verification_date
                ),
                VerificationEntryModel.employee_id == employee_id)

        res = await self._session.execute(stmt)
        return res.unique().scalar_one_or_none()

    async def get_for_display(
        self,
        metrolog_info_id: int,
        verification_entry_id: int,
        employee_id: int | None,
        status,
    ) -> MetrologInfoModel | None:
        """Get metrolog info for display in templates (no lock)."""
        stmt = (
            select(MetrologInfoModel)
            .join(MetrologInfoModel.verification)
            .join(VerificationEntryModel.company)
            .options(
                # Load all MetrologInfoModel columns for template
                contains_eager(MetrologInfoModel.verification)
                .load_only(
                    VerificationEntryModel.id,
                    VerificationEntryModel.company_id,
                    VerificationEntryModel.verifier_id,
                    VerificationEntryModel.employee_id,
                    VerificationEntryModel.reason_id,
                    VerificationEntryModel.verification_result,
                    VerificationEntryModel.verification_date,
                ).options(
                    selectinload(VerificationEntryModel.equipments)
                    .load_only(
                        EquipmentModel.id,
                        EquipmentModel.name,
                        EquipmentModel.factory_number,
                    ).joinedload(EquipmentModel.equipment_info)
                    .load_only(
                        EquipmentInfoModel.id,
                        EquipmentInfoModel.type,
                        EquipmentInfoModel.date_to,
                    ),
                    joinedload(VerificationEntryModel.reason)
                    .load_only(
                        ReasonModel.full_name,
                        ReasonModel.type,
                    )
                )
            )
            .where(
                MetrologInfoModel.id == metrolog_info_id,
                MetrologInfoModel.company_id == self._company_id,
                MetrologInfoModel.verification_id == verification_entry_id
            )
        )

        if status in auditor_verifier:
            stmt = stmt.where(
                VerificationEntryModel.company.has(
                    CompanyModel.verification_date_block <
                    VerificationEntryModel.verification_date
                ),
                VerificationEntryModel.employee_id == employee_id
            )

        res = await self._session.execute(stmt)
        return res.unique().scalar_one_or_none()

    async def get_for_update(
        self,
        metrolog_info_id: int,
        verification_entry_id: int,
        employee_id: int | None,
        status,
    ) -> MetrologInfoModel | None:
        stmt = (
            select(MetrologInfoModel)
            .join(MetrologInfoModel.verification)
            .join(VerificationEntryModel.company)
            .options(
                contains_eager(MetrologInfoModel.verification)
                .load_only(
                    VerificationEntryModel.id,
                    VerificationEntryModel.company_id,
                    VerificationEntryModel.verifier_id,
                    VerificationEntryModel.employee_id,
                    VerificationEntryModel.reason_id,
                    VerificationEntryModel.verification_result,
                    VerificationEntryModel.verification_date,
                ).options(
                    selectinload(VerificationEntryModel.equipments)
                    .load_only(
                        EquipmentModel.id,
                        EquipmentModel.name,
                        EquipmentModel.factory_number,
                    ).joinedload(EquipmentModel.equipment_info)
                    .load_only(
                        EquipmentInfoModel.id,
                        EquipmentInfoModel.type,
                        EquipmentInfoModel.date_to,
                    ),
                    joinedload(VerificationEntryModel.reason)
                    .load_only(
                        ReasonModel.full_name,
                        ReasonModel.type,
                    )
                )
            )
            .where(
                MetrologInfoModel.id == metrolog_info_id,
                MetrologInfoModel.company_id == self._company_id,
                MetrologInfoModel.verification_id == verification_entry_id
            )
            .with_for_update(of=MetrologInfoModel)
        )

        if status in auditor_verifier:
            stmt = stmt.where(
                VerificationEntryModel.company.has(
                    CompanyModel.verification_date_block <
                    VerificationEntryModel.verification_date
                ),
                VerificationEntryModel.employee_id == employee_id
            )

        res = await self._session.execute(stmt)
        return res.unique().scalar_one_or_none()

    async def try_delete_entry(
        self, metrolog_info_id: int,
        verification_entry_id: int,
        employee_id: int | None,
        status,
    ) -> bool:
        conds = [
            MetrologInfoModel.id == metrolog_info_id,
            MetrologInfoModel.company_id == self._company_id,
            MetrologInfoModel.verification_id == verification_entry_id,
        ]

        if status not in admin_director:
            conds.append(
                MetrologInfoModel.verification.has(
                    VerificationEntryModel.employee_id == employee_id,
                    VerificationEntryModel.company.has(
                        CompanyModel.verification_date_block <
                        VerificationEntryModel.verification_date
                    ),
                )
            )

        stmt = delete(MetrologInfoModel).where(*conds).returning(MetrologInfoModel.id)
        res = await self._session.scalar(stmt)
        return bool(res)


async def read_metrolog_info_repository(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    session: AsyncSession = Depends(async_db_session),
) -> MetrologInfoRepository:
    return MetrologInfoRepository(session=session, company_id=company_id)


async def action_metrolog_info_repository(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    session: AsyncSession = Depends(async_db_session_begin),
) -> MetrologInfoRepository:
    return MetrologInfoRepository(session=session, company_id=company_id)
