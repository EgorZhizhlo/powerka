from fastapi import (
    APIRouter, Response, status as status_code,
    Depends, Query, Body
)

from access_control import (
    JwtData,
    check_include_in_active_company,
    check_companies_access,
    bump_jwt_token_version
)

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from core.utils.time_utils import date_utc_now
from core.exceptions import CustomHTTPException, check_is_none
from infrastructure.cache import redis
from core.config import settings
from core.cache.company_timezone_cache import company_tz_cache

from infrastructure.db import async_db_session_begin
from models.enums import EmployeeStatus
from models import (
    EmployeeModel, CompanyModel, VerifierModel, VerificationLogModel,
    CompanyCalendarParameterModel
)

from apps.company_app.common import (
    _register_delete_vote, _clear_delete_votes, _try_acquire_delete_lock,
    _release_delete_lock, _company_delete_key,
    action_with_ya_disk,
    check_employee_limit_available,
    recalculate_employee_count
)

from apps.company_app.schemas.companies_menu import (
    EditCompanyFormDirector, EditCompanyFormAdmin
)


companies_menu_api_router = APIRouter(
    prefix="/api"
)


@companies_menu_api_router.post("/create")
async def api_create_company(
    user_data: JwtData = Depends(check_companies_access),
    session: AsyncSession = Depends(async_db_session_begin),
    admin_form: EditCompanyFormAdmin = Body(...),
):
    if user_data.status != EmployeeStatus.admin:
        raise CustomHTTPException(
            status_code=403,
            detail="Доступ только для администратора")

    assigned_employee_ids: set[int] = set()
    company = CompanyModel(
        employees=[],
        is_active=False
    )

    for key, value in admin_form.model_dump(exclude_none=True).items():
        if hasattr(CompanyModel, key):
            setattr(company, key, value)

    if admin_form.daily_verifier_verif_limit is None:
        company.daily_verifier_verif_limit = 0

    ids = admin_form.employee_ids or []
    if ids:
        employees = (await session.execute(
            select(EmployeeModel).where(EmployeeModel.id.in_(ids))
        )).scalars().all()
        company.employees = employees
        assigned_employee_ids = {e.id for e in employees}
    else:
        company.employees = []

    session.add(company)
    await session.flush()
    await session.refresh(company)

    # Кешируем timezone компании
    await company_tz_cache.set_timezone(company.id, company.timezone)

    params = CompanyCalendarParameterModel(company_id=company.id)
    for key, value in admin_form.model_dump().items():
        if hasattr(CompanyCalendarParameterModel, key):
            setattr(params, key, bool(value))
    session.add(params)

    if admin_form.yandex_disk_token:
        await action_with_ya_disk(
            token=admin_form.yandex_disk_token,
            company_id=company.id,
            old_company_name=None,
            new_company_name=company.name
        )

    for uid in assigned_employee_ids:
        await bump_jwt_token_version(f"user:{uid}:company_version")

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@companies_menu_api_router.put("/update")
async def api_update_company(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
    director_form: EditCompanyFormDirector = Body(None),
    admin_form: EditCompanyFormAdmin = Body(None),
):
    status = user_data.status

    # Проверяем что хотя бы одна форма пришла
    if director_form is None and admin_form is None:
        raise CustomHTTPException(
            status_code=400,
            detail="Необходимо передать данные формы",
            company_id=company_id
        )

    # Выбираем форму в зависимости от роли
    if status == EmployeeStatus.director:
        if director_form is None:
            raise CustomHTTPException(
                status_code=400,
                detail="Для директора необходима форма director_form",
                company_id=company_id
            )
        form_data = director_form
    else:  # admin
        if admin_form is None:
            raise CustomHTTPException(
                status_code=400,
                detail="Для администратора необходима форма admin_form",
                company_id=company_id
            )
        form_data = admin_form

    old_employee_ids: set[int] = set()
    new_employee_ids: set[int] = set()

    company = (
        await session.execute(
            select(CompanyModel)
            .where(CompanyModel.id == company_id)
            .options(
                selectinload(CompanyModel.activities),
                selectinload(CompanyModel.si_types),
                selectinload(CompanyModel.employees),
            )
        )
    ).scalar_one_or_none()

    params = (await session.execute(
        select(CompanyCalendarParameterModel)
        .where(CompanyCalendarParameterModel.company_id == company_id)
    )).scalar_one_or_none()
    if not params:
        params = CompanyCalendarParameterModel(company_id=company_id)
        session.add(params)

    await check_is_none(
        company, type="Компания", id=company_id, company_id=company_id)

    old_company_name = company.name
    old_employee_ids = {e.id for e in (company.employees or [])}

    if (form_data.daily_verifier_verif_limit is not None and
            company.daily_verifier_verif_limit !=
            form_data.daily_verifier_verif_limit):
        date_today = date_utc_now()
        daily_verifier_verif_limit = company.daily_verifier_verif_limit
        new_daily_verifier_verif_limit = form_data.daily_verifier_verif_limit
        verifier_id_list = (
            await session.execute(
                select(VerifierModel.id).where(
                    VerifierModel.company_id == company_id)
            )
        ).scalars().all()

        verification_log = (
            await session.execute(
                select(VerificationLogModel)
                .where(
                    VerificationLogModel.verifier_id.in_(
                        list(verifier_id_list)),
                    VerificationLogModel.verification_date == date_today
                )
            )
        ).scalars().all()

        for log in verification_log:
            log.verification_limit = new_daily_verifier_verif_limit - \
                abs(daily_verifier_verif_limit - log.verification_limit)

    for key, value in form_data.model_dump(exclude_none=True).items():
        if hasattr(CompanyModel, key):
            setattr(company, key, value)

    if status == EmployeeStatus.admin:
        ids = admin_form.employee_ids or []
        employees = []
        if ids:
            employees = (await session.execute(
                select(EmployeeModel).where(EmployeeModel.id.in_(ids))
            )).scalars().all()

        company.employees = employees
        new_employee_ids = {e.id for e in employees}

    session.add(company)
    await session.flush()
    await session.refresh(company)

    # Обновляем timezone в кеше (важно после flush/refresh)
    await company_tz_cache.refresh_timezone(company_id, session)

    new_company_name = company.name

    for key, value in form_data.model_dump().items():
        if hasattr(CompanyCalendarParameterModel, key):
            setattr(params, key, bool(value))

    if form_data.yandex_disk_token:
        await action_with_ya_disk(
            token=form_data.yandex_disk_token,
            company_id=company_id,
            old_company_name=old_company_name,
            new_company_name=new_company_name
        )

    removed_ids = old_employee_ids - new_employee_ids
    added_ids = new_employee_ids - old_employee_ids

    # Проверка лимита: учитываем ЧИСТОЕ изменение (добавленные - удаленные)
    if status == EmployeeStatus.admin:
        net_change = len(added_ids) - len(removed_ids)

        # Проверяем лимит только если чистое увеличение > 0
        if net_change > 0:
            await check_employee_limit_available(
                session, company_id, required_slots=net_change
            )

        # Всегда пересчитываем для синхронизации
        await recalculate_employee_count(session, company_id)

    to_bump = set()

    if status == EmployeeStatus.admin:
        to_bump = removed_ids | added_ids

    for uid in to_bump:
        await bump_jwt_token_version(f"user:{uid}:company_version")

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@companies_menu_api_router.delete("/delete")
async def api_delete_company(

    company_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(
        check_include_in_active_company
    ),
    session: AsyncSession = Depends(async_db_session_begin),
):
    if user_data.status != EmployeeStatus.admin:
        raise CustomHTTPException(
            status_code=403, detail="Доступ только для администратора")

    company = (
        await session.execute(
            select(CompanyModel)
            .where(CompanyModel.id == company_id)
            .options(selectinload(CompanyModel.employees))
        )
    ).scalar_one_or_none()
    await check_is_none(
        company, type="Компания", id=company_id, company_id=company_id)

    votes = await _register_delete_vote(company_id, user_data.id)
    if votes < 2:
        return Response(status_code=status_code.HTTP_202_ACCEPTED)

    if not await _try_acquire_delete_lock(company_id):
        return Response(status_code=status_code.HTTP_409_CONFLICT)

    affected_employee_ids = {e.id for e in (company.employees or [])}

    try:
        deletable_employees = (
            await session.execute(
                select(EmployeeModel)
                .where(
                    EmployeeModel.status != EmployeeStatus.admin,
                    EmployeeModel.companies.any(
                        CompanyModel.id == company_id),
                    ~EmployeeModel.companies.any(
                        CompanyModel.id != company_id),
                )
            )
        ).scalars().all()

        for emp in deletable_employees:
            await session.delete(emp)

        await session.delete(company)
        await _clear_delete_votes(company_id)

        # Инвалидируем кеш тарифов и timezone
        from apps.tariff_app.services.tariff_cache import tariff_cache
        await tariff_cache.invalidate_cache(company_id)
        await company_tz_cache.invalidate_timezone(company_id)

    finally:
        await _release_delete_lock(company_id)

    for uid in affected_employee_ids:
        await bump_jwt_token_version(f"user:{uid}:company_version")
    await bump_jwt_token_version(f"user:{user_data.id}:company_version")

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@companies_menu_api_router.post("/cancel")
async def api_cancel_delete_company(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(
        check_include_in_active_company
    ),
):
    if user_data.status != EmployeeStatus.admin:
        raise CustomHTTPException(
            status_code=403, detail="Доступ только для администратора")

    key = _company_delete_key(company_id)
    await redis.srem(key, str(user_data.id))
    if await redis.scard(key) == 0:
        await redis.delete(key)

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)
