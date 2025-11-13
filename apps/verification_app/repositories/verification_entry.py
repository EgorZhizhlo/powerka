from fastapi import Depends, Query
from typing import Optional, List, Tuple, Any
from math import ceil
from datetime import date as date_
from sqlalchemy import select, delete, exists, func, case
from sqlalchemy.orm import selectinload, joinedload, load_only, contains_eager
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.db import async_db_session_begin, async_db_session
from models.enums import EmployeeStatus
from models import (
    VerificationEntryModel,
    MetrologInfoModel,
    EquipmentModel,
    EquipmentInfoModel,
    CompanyModel,
    ReasonModel,
    SiModificationModel,
    MethodModel,
    RegistryNumberModel,
    ActNumberModel,
    CityModel,
    VerifierModel,
    VerificationEntryPhotoModel,
    LocationModel,
    EmployeeModel,
    ActSeriesModel
)

from core.config import settings

from access_control import admin_director, verifier


class VerificationEntryRepository:
    def __init__(self, session: AsyncSession, company_id: int):
        self._session = session
        self._company_id = company_id

    async def _apply_role_filter(
            self, stmt, status: str | None, employee_id: int | None):
        if status == EmployeeStatus.verifier and employee_id is not None:
            stmt = stmt.where(
                VerificationEntryModel.employee_id == employee_id
            )
        return stmt

    async def exists_entry_by_factory_num(
        self, factory_number: str, verification_date: date_,
        exclude_entry_id: Optional[int] = None,
    ) -> bool:
        factory_number = func.lower(factory_number)

        conditions = [
            VerificationEntryModel.company_id == self._company_id,
            func.lower(
                VerificationEntryModel.factory_number) == factory_number,
            VerificationEntryModel.verification_date == verification_date,
        ]
        if exclude_entry_id is not None:
            conditions.append(VerificationEntryModel.id != exclude_entry_id)

        stmt = select(exists().where(*conditions))

        return await self._session.scalar(stmt)

    async def get_by_id(
            self, verification_entry_id: int
    ) -> VerificationEntryModel | None:
        stmt = (
            select(VerificationEntryModel)
            .where(
                VerificationEntryModel.id == verification_entry_id,
                VerificationEntryModel.company_id == self._company_id
            )
            .options(
                joinedload(VerificationEntryModel.series).load_only(
                    ActSeriesModel.name
                ),
                joinedload(VerificationEntryModel.act_number).load_only(
                    ActNumberModel.act_number
                ),
                joinedload(VerificationEntryModel.verifier).load_only(
                    VerifierModel.last_name,
                    VerifierModel.name,
                    VerifierModel.patronymic,
                ),
            )
        )

        result = await self._session.execute(stmt)
        entry = result.scalars().first()

        return entry

    async def get_counts(
        self,
        filter=None,
        employee_id: int | None = None,
        status: str | None = None,
    ) -> tuple[int, int]:
        from apps.verification_app.common.filter_functions import entry_filter

        count_stmt = (
            select(
                func.count().label("total"),
                func.sum(
                    case(
                        (
                            VerificationEntryModel.verification_result.is_(
                                True
                            ),
                            1
                        ),
                        else_=0
                    )
                ).label("verified")
            )
            .where(VerificationEntryModel.company_id == self._company_id)
        )

        if filter is not None:
            count_stmt = await entry_filter(count_stmt, filter)

        count_stmt = await self._apply_role_filter(
            count_stmt, status, employee_id
        )

        res = await self._session.execute(count_stmt)
        row = res.mappings().first() or {}
        total_entries = int(row.get("total") or 0)
        verified_entries = int(row.get("verified") or 0)
        return total_entries, verified_entries

    async def get_all(
        self,
        page: int = 1,
        limit: int = 30,
        filter=None,
        employee_id: int | None = None,
        status: str | None = None,
    ) -> Tuple[Any]:
        from apps.verification_app.common.filter_functions import entry_filter

        offset = (page - 1) * limit

        stmt = (
            select(VerificationEntryModel)
            .where(VerificationEntryModel.company_id == self._company_id)
            .options(
                load_only(
                    VerificationEntryModel.id,
                    VerificationEntryModel.company_id,
                    VerificationEntryModel.verification_date,
                    VerificationEntryModel.factory_number,
                    VerificationEntryModel.meter_info,
                    VerificationEntryModel.end_verification_date,
                    VerificationEntryModel.verification_result,
                    VerificationEntryModel.water_type,
                    VerificationEntryModel.seal,
                    VerificationEntryModel.manufacture_year,
                    VerificationEntryModel.created_at,
                    VerificationEntryModel.updated_at,
                ),
                joinedload(VerificationEntryModel.employee).load_only(
                    EmployeeModel.id,
                    EmployeeModel.last_name,
                    EmployeeModel.name,
                    EmployeeModel.patronymic,
                ),
                joinedload(VerificationEntryModel.city).load_only(
                    CityModel.id,
                    CityModel.name
                ),
                joinedload(VerificationEntryModel.act_number).load_only(
                    ActNumberModel.id,
                    ActNumberModel.act_number,
                    ActNumberModel.address,
                    ActNumberModel.client_full_name,
                ),
                joinedload(VerificationEntryModel.registry_number).load_only(
                    RegistryNumberModel.id,
                    RegistryNumberModel.si_type,
                    RegistryNumberModel.registry_number,
                ),
                joinedload(VerificationEntryModel.modification).load_only(
                    SiModificationModel.id,
                    SiModificationModel.modification_name,
                ),
                joinedload(VerificationEntryModel.location).load_only(
                    LocationModel.id,
                    LocationModel.name
                ),
                joinedload(VerificationEntryModel.series).load_only(
                    ActSeriesModel.id,
                    ActSeriesModel.name,
                ),
                joinedload(VerificationEntryModel.metrolog).load_only(
                    MetrologInfoModel.id,
                ),
            )
            .order_by(
                VerificationEntryModel.verification_date.desc(),
                VerificationEntryModel.id.desc(),
            )
        )

        if filter is not None:
            stmt = await entry_filter(stmt, filter)

        stmt = await self._apply_role_filter(stmt, status, employee_id)

        stmt = stmt.offset(offset).limit(limit)

        result = await self._session.execute(stmt)
        entries: List[VerificationEntryModel] = result.scalars().all()

        total_entries, verified_entries = await self.get_counts(
            filter=filter, employee_id=employee_id, status=status
        )

        total_pages = ceil(total_entries / limit) if total_entries else 1

        return (
            entries,
            page,
            limit,
            total_pages,
            total_entries,
            verified_entries
        )

    async def get_to_update(
        self,
        verification_entry_id: int,
        employee_id: int,
        status: str,
    ) -> VerificationEntryModel | None:
        stmt = (
            select(VerificationEntryModel)
            .where(
                VerificationEntryModel.id == verification_entry_id,
                VerificationEntryModel.company_id == self._company_id,
            )
            .options(
                selectinload(VerificationEntryModel.verifier).load_only(
                    VerifierModel.id,
                    VerifierModel.last_name,
                    VerifierModel.name,
                    VerifierModel.patronymic,
                ).selectinload(VerifierModel.equipments).load_only(
                    EquipmentModel.id,
                    EquipmentModel.name,
                    EquipmentModel.factory_number,
                ).joinedload(EquipmentModel.equipment_info).load_only(
                    EquipmentInfoModel.id,
                    EquipmentInfoModel.verif_limit_date,
                    EquipmentInfoModel.type
                ),
                joinedload(VerificationEntryModel.company).load_only(
                    CompanyModel.name,
                    CompanyModel.yandex_disk_token,
                    CompanyModel.verification_date_block,
                ),
                joinedload(VerificationEntryModel.series).load_only(
                    ActSeriesModel.name
                ),
                joinedload(VerificationEntryModel.act_number).load_only(
                    ActNumberModel.act_number,
                    ActNumberModel.count,
                    ActNumberModel.client_full_name,
                    ActNumberModel.address,
                ).joinedload(ActNumberModel.city).load_only(
                    CityModel.id,
                    CityModel.name
                ),
                joinedload(VerificationEntryModel.reason).load_only(
                    ReasonModel.id,
                    ReasonModel.full_name,
                    ReasonModel.type,
                ),
                joinedload(VerificationEntryModel.method).load_only(
                    MethodModel.id,
                    MethodModel.name,
                ),
                joinedload(VerificationEntryModel.registry_number).load_only(
                    RegistryNumberModel.id,
                    RegistryNumberModel.registry_number,
                ),
                selectinload(VerificationEntryModel.equipments).load_only(
                    EquipmentModel.id,
                    EquipmentModel.is_opt
                ),
                selectinload(
                    VerificationEntryModel.verification_entry_photo
                ).load_only(
                    VerificationEntryPhotoModel.id,
                    VerificationEntryPhotoModel.file_name,
                    VerificationEntryPhotoModel.url,
                ),
            )
            .with_for_update(of=VerificationEntryModel)
        )

        if status not in admin_director:
            stmt = stmt.where(
                VerificationEntryModel.employee_id == employee_id,
                CompanyModel.verification_date_block
                < VerificationEntryModel.verification_date,
            )

        res = await self._session.execute(stmt)
        return res.unique().scalar_one_or_none()

    async def get_for_delete(
        self,
        verification_entry_id: int,
        employee_id: int | None,
        status,
    ) -> VerificationEntryModel | None:
        stmt = (
            select(VerificationEntryModel)
            .where(
                VerificationEntryModel.id == verification_entry_id,
                VerificationEntryModel.company_id == self._company_id,
            )
            .options(
                load_only(
                    VerificationEntryModel.id,
                    VerificationEntryModel.verification_date,
                    VerificationEntryModel.employee_id,
                    VerificationEntryModel.verifier_id,
                    VerificationEntryModel.series_id,
                    VerificationEntryModel.act_number_id,
                    VerificationEntryModel.location_id,
                    VerificationEntryModel.company_id,
                ),
                joinedload(VerificationEntryModel.company).load_only(
                    CompanyModel.name,
                    CompanyModel.yandex_disk_token,
                    CompanyModel.verification_date_block,
                ),
                joinedload(VerificationEntryModel.verifier).load_only(
                    VerifierModel.last_name,
                    VerifierModel.name,
                    VerifierModel.patronymic,
                ),
                joinedload(VerificationEntryModel.series).load_only(
                    ActSeriesModel.name
                ),
                joinedload(VerificationEntryModel.act_number).load_only(
                    ActNumberModel.act_number,
                    ActNumberModel.count,
                ),
            )
            .with_for_update(of=VerificationEntryModel)
        )

        if status not in admin_director:
            stmt = stmt.where(
                VerificationEntryModel.employee_id == employee_id,
                CompanyModel.verification_date_block
                < VerificationEntryModel.verification_date,
            )

        res = await self._session.execute(stmt)
        return res.unique().scalar_one_or_none()

    async def delete_related(self, verification_entry_id: int):
        await self._session.execute(
            delete(VerificationEntryPhotoModel).where(
                VerificationEntryPhotoModel.verification_entry_id
                == verification_entry_id
            )
        )
        await self._session.execute(
            delete(MetrologInfoModel).where(
                MetrologInfoModel.verification_id == verification_entry_id
            )
        )

    async def delete_entry(self, verification_entry_id: int):
        await self._session.execute(
            delete(VerificationEntryModel).where(
                VerificationEntryModel.id == verification_entry_id
            )
        )

    async def delete_all_with_act(self, act_number_id: int):
        await self._session.execute(
            delete(VerificationEntryModel).where(
                VerificationEntryModel.act_number_id == act_number_id
            )
        )
        await self._session.execute(
            delete(ActNumberModel).where(ActNumberModel.id == act_number_id)
        )

    async def get_for_protocol(
        self,
        verification_entry_id: int,
        metrolog_info_id: int,
        employee_id: int | None,
        status,
    ) -> VerificationEntryModel | None:
        stmt = (
            select(VerificationEntryModel)
            .join(VerificationEntryModel.metrolog)
            .where(
                MetrologInfoModel.id == metrolog_info_id,
                VerificationEntryModel.company_id == self._company_id,
                VerificationEntryModel.id == verification_entry_id,
            )
            .options(
                load_only(
                    VerificationEntryModel.id,
                    VerificationEntryModel.manufacture_year,
                    VerificationEntryModel.interval,
                    VerificationEntryModel.verification_date,
                    VerificationEntryModel.verification_number,
                    VerificationEntryModel.factory_number,
                    VerificationEntryModel.employee_id,
                    VerificationEntryModel.verifier_id,
                    VerificationEntryModel.updated_at
                ),
                contains_eager(VerificationEntryModel.metrolog),
                joinedload(VerificationEntryModel.verifier).load_only(
                    VerifierModel.last_name,
                    VerifierModel.name,
                    VerifierModel.patronymic,
                ),
                joinedload(VerificationEntryModel.reason).load_only(
                    ReasonModel.id,
                    ReasonModel.type,
                    ReasonModel.full_name
                ),
                joinedload(VerificationEntryModel.modification).load_only(
                    SiModificationModel.id,
                    SiModificationModel.modification_name
                ),
                joinedload(VerificationEntryModel.method).load_only(
                    MethodModel.id,
                    MethodModel.name
                ),
                joinedload(VerificationEntryModel.registry_number).load_only(
                    RegistryNumberModel.id,
                    RegistryNumberModel.si_type,
                    RegistryNumberModel.registry_number,
                ),
                joinedload(VerificationEntryModel.company).load_only(
                    CompanyModel.id,
                    CompanyModel.name,
                    CompanyModel.accreditation_certificat,
                    CompanyModel.address,
                ),
                joinedload(VerificationEntryModel.act_number).load_only(
                    ActNumberModel.id,
                    ActNumberModel.client_full_name,
                    ActNumberModel.address,
                ),
                joinedload(VerificationEntryModel.city).load_only(
                    CityModel.id,
                    CityModel.name
                ),
                selectinload(VerificationEntryModel.equipments).load_only(
                    EquipmentModel.id,
                    EquipmentModel.name,
                    EquipmentModel.register_number,
                    EquipmentModel.factory_number,
                    EquipmentModel.list_number,
                    EquipmentModel.type,
                ).joinedload(EquipmentModel.equipment_info).load_only(
                    EquipmentInfoModel.id,
                    EquipmentInfoModel.type,
                    EquipmentInfoModel.verif_limit_date,
                ),
            )
        )

        if status in verifier:
            stmt = stmt.where(
                VerificationEntryModel.employee_id == employee_id)

        res = await self._session.execute(stmt)
        return res.unique().scalar_one_or_none()

    async def get_for_protocols(
        self,
        date_from: date_ | None = None,
        date_to: date_ | None = None,
        series_id: int | None = None,
        employee_id: int | None = None,
    ) -> list[VerificationEntryModel]:
        stmt = (
            select(VerificationEntryModel)
            .join(VerificationEntryModel.metrolog)
            .where(
                VerificationEntryModel.company_id == self._company_id,
            )
            .options(
                load_only(
                    VerificationEntryModel.id,
                    VerificationEntryModel.verification_number,
                    VerificationEntryModel.verification_date,
                    VerificationEntryModel.factory_number,
                    VerificationEntryModel.verification_result,
                    VerificationEntryModel.interval,
                    VerificationEntryModel.manufacture_year,
                    VerificationEntryModel.updated_at,
                    VerificationEntryModel.verifier_id,
                ),
                contains_eager(VerificationEntryModel.metrolog),
                joinedload(VerificationEntryModel.verifier).load_only(
                    VerifierModel.id,
                    VerifierModel.last_name,
                    VerifierModel.name,
                    VerifierModel.patronymic,
                ),
                joinedload(VerificationEntryModel.reason).load_only(
                    ReasonModel.id,
                    ReasonModel.full_name,
                    ReasonModel.type,
                ),
                joinedload(VerificationEntryModel.modification).load_only(
                    SiModificationModel.id,
                    SiModificationModel.modification_name,
                ),
                joinedload(VerificationEntryModel.method).load_only(
                    MethodModel.id,
                    MethodModel.name,
                ),
                joinedload(VerificationEntryModel.registry_number).load_only(
                    RegistryNumberModel.id,
                    RegistryNumberModel.si_type,
                    RegistryNumberModel.registry_number,
                ),
                joinedload(VerificationEntryModel.company).load_only(
                    CompanyModel.id,
                    CompanyModel.name,
                    CompanyModel.accreditation_certificat,
                    CompanyModel.address,
                ),
                joinedload(VerificationEntryModel.act_number).load_only(
                    ActNumberModel.id,
                    ActNumberModel.client_full_name,
                    ActNumberModel.address,
                ),
                joinedload(VerificationEntryModel.city).load_only(
                    CityModel.id,
                    CityModel.name,
                ),
                selectinload(VerificationEntryModel.equipments).load_only(
                    EquipmentModel.id,
                    EquipmentModel.name,
                    EquipmentModel.register_number,
                    EquipmentModel.factory_number,
                    EquipmentModel.list_number,
                    EquipmentModel.type,
                ).joinedload(EquipmentModel.equipment_info).load_only(
                    EquipmentInfoModel.id,
                    EquipmentInfoModel.type,
                    EquipmentInfoModel.verif_limit_date,
                ),
            )
        )

        if date_from:
            stmt = stmt.where(
                VerificationEntryModel.verification_date >= date_from)
        if date_to:
            stmt = stmt.where(
                VerificationEntryModel.verification_date <= date_to)
        if series_id:
            stmt = stmt.where(
                VerificationEntryModel.series_id == series_id)
        if employee_id:
            stmt = stmt.where(
                VerificationEntryModel.employee_id == employee_id)

        stmt = stmt.order_by(
            VerificationEntryModel.verification_date.desc(),
            VerificationEntryModel.id.desc()
        )

        res = await self._session.execute(stmt)
        return res.unique().scalars().all()


async def read_verification_entry_repository(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    session: AsyncSession = Depends(async_db_session),
) -> VerificationEntryRepository:
    return VerificationEntryRepository(session=session, company_id=company_id)


async def action_verification_entry_repository(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    session: AsyncSession = Depends(async_db_session_begin),
) -> VerificationEntryRepository:
    return VerificationEntryRepository(session=session, company_id=company_id)
