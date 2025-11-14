from typing import List, Dict, Any
import json
import hashlib
from fastapi import (
    APIRouter, Response, HTTPException, UploadFile,
    Body, File, Depends, Query
)
from fastapi.encoders import jsonable_encoder

from sqlalchemy import select, delete, exists
from sqlalchemy.ext.asyncio import AsyncSession

from access_control import (
    JwtData,
    check_access_verification,
    check_active_access_verification,
    admin_director
)

from infrastructure.cache import redis
from infrastructure.db import async_db_session_begin
from infrastructure.yandex_disk.service import get_yandex_service

from models import (
    VerificationEntryModel, MetrologInfoModel,
    ActNumberModel
)
from models.enums import ReasonType

from core.config import settings
from core.db.dependencies import get_company_timezone
from core.utils.time_utils import validate_company_timezone
from core.exceptions import (
    CompanyVerificationLimitException,
)

from apps.verification_app.exceptions import (
    VerificationEntryException,
    VerificationVerifierException,
    VerificationEquipmentException,
    CreateVerificationCitiesBlockException,
    CreateVerificationDateBlockException,
    CreateVerificationFactoryNumBlockException,
    CreateVerificationDefaultVerifierException,
    UpdateVerificationVerNumBlockException,
    DeleteVerificationEntryAccessException,
)
from apps.verification_app.common import (
    check_equip_conditions, act_number_for_create, check_act_number_limit,
    get_verifier_id_create, right_automatisation_metrolog,

    check_similarity_act_numbers, update_existed_act_number,
    act_number_for_update, apply_verifier_log_delta,

    clear_verification_cache,
    check_verification_limit_available,
    increment_verification_count,
    decrement_verification_count
)
from apps.verification_app.repositories import (
    EmployeeCitiesRepository, read_employee_cities_repository,
    CompanyRepository, read_company_repository,
    VerificationEntryRepository,
    read_verification_entry_repository,
    action_verification_entry_repository,
    VerifierRepository, read_verifier_repository,
    EquipmentRepository, action_equipment_repository,
    LocationRepository, action_location_repository,
    VerificationLogRepository, action_verification_log_repository,
)
from apps.verification_app.services import process_act_number_photos
from apps.verification_app.schemas.verifications_control import (
    VerificationEntryFilter, VerificationEntryListOut, VerificationEntryOut,
    CreateVerificationEntryForm, UpdateVerificationEntryForm,
    MetrologInfoForm
)


verifications_control_api_router = APIRouter(
    prefix='/api/verifications-control')
VER_PHOTO_LIMIT: int = settings.image_limit_per_verification
ALLOWED_PHOTO_EXT: set[str] = settings.allowed_photo_ext


@verifications_control_api_router.get(
    "/", response_model=VerificationEntryListOut
)
async def get_verification_entries(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    verif_entry_filter: VerificationEntryFilter = Depends(),
    employee_data: JwtData = Depends(check_access_verification),
    company_tz: str = Depends(get_company_timezone),
    verification_entry_repo: VerificationEntryRepository = Depends(
        read_verification_entry_repository),
):
    filters_json = json.dumps(
        jsonable_encoder(verif_entry_filter.model_dump()),
        sort_keys=True
    )
    filters_hash = hashlib.md5(filters_json.encode()).hexdigest()

    cache_key = f"verification_entries:{company_id}:{filters_hash}:{verif_entry_filter.page or 1}:{verif_entry_filter.limit or 30}"

    cached = await redis.get(cache_key)
    if cached:
        try:
            data = json.loads(cached)
            return VerificationEntryListOut(**data)
        except Exception:
            await redis.delete(cache_key)

    result = await verification_entry_repo.get_all(
        page=verif_entry_filter.page or 1,
        limit=verif_entry_filter.limit or 30,
        filter=verif_entry_filter,
        employee_id=employee_data.id,
        status=employee_data.status,
    )
    entries, page, limit, total_pages, total_entries, verified_entries = result

    from core.templates.jinja_filters import format_datetime_tz

    items = []
    for entry in entries:
        item = VerificationEntryOut.model_validate(entry)
        item.created_at_formatted = format_datetime_tz(
            entry.created_at, company_tz, "%d.%m.%Y %H:%M"
        )
        item.updated_at_formatted = format_datetime_tz(
            entry.updated_at, company_tz, "%d.%m.%Y %H:%M"
        )
        items.append(item)

    data = VerificationEntryListOut(
        company_id=company_id,
        items=items,
        page=page,
        limit=limit,
        total_pages=total_pages,
        total_entries=total_entries,
        verified_entry=verified_entries,
        not_verified_entry=total_entries - verified_entries,
    )

    await redis.set(cache_key, data.model_dump_json(), ex=60)

    return data


@verifications_control_api_router.post("/create")
async def create_verification_entry(
    verification_entry_data: CreateVerificationEntryForm = Body(...),
    new_images: List[UploadFile] = File(default_factory=list),

    company_id: int = Query(..., ge=1, le=settings.max_int),
    redirect_to_metrolog_info: bool = Query(...),

    company_tz: str = Depends(get_company_timezone),
    session: AsyncSession = Depends(async_db_session_begin),

    employee_data: JwtData = Depends(
        check_active_access_verification),
    empl_cities_repo: EmployeeCitiesRepository = Depends(
        read_employee_cities_repository
    ),
    company_repo: CompanyRepository = Depends(
        read_company_repository
    ),
    verification_entry_repo: VerificationEntryRepository = Depends(
        action_verification_entry_repository
    ),
    verifier_repo: VerifierRepository = Depends(
        read_verifier_repository
    ),
    location_repo: LocationRepository = Depends(
        action_location_repository
    ),
    equipment_repo: EquipmentRepository = Depends(
        action_equipment_repository
    )
):
    status = employee_data.status
    employee_id = employee_data.id

    validate_company_timezone(
        verification_entry_data.company_tz,
        company_tz,
        company_id
    )

    await check_verification_limit_available(
        session=session,
        company_id=company_id,
        required_slots=1
    )

    employee_cities_id = await empl_cities_repo.get_cities_id(employee_id)
    if employee_cities_id and verification_entry_data.city_id \
            and verification_entry_data.city_id not in employee_cities_id:
        raise CreateVerificationCitiesBlockException

    company_params = await company_repo.get_company_params()

    if status not in admin_director:
        verif_date_block = company_params.verification_date_block
        if verif_date_block and verif_date_block >= \
                verification_entry_data.verification_date:
            raise CreateVerificationDateBlockException

    new_factory_number = verification_entry_data.factory_number
    new_verification_date = verification_entry_data.verification_date

    exists_factory = await verification_entry_repo.exists_entry_by_factory_num(
        factory_number=new_factory_number,
        verification_date=new_verification_date
    )
    if exists_factory:
        raise CreateVerificationFactoryNumBlockException

    default_verifier = await verifier_repo.default_verifier_for_create(
        employee_id=employee_id
    )
    if not default_verifier:
        raise CreateVerificationDefaultVerifierException

    await check_equip_conditions(
        default_verifier.equipments, company_id=company_id
    )

    act_number_entry = await act_number_for_create(
        company_id=company_id,
        entry_data=verification_entry_data,
        session=session
    )
    check_act_number_limit(
        act_number_entry=act_number_entry
    )
    act_number_entry.count -= 1

    verifier_id = default_verifier.id

    if company_params.auto_teams:
        verification_limit = company_params.daily_verifier_verif_limit
        if not verification_limit or verification_limit < 0:
            raise CompanyVerificationLimitException

        verification_date = verification_entry_data.verification_date

        verifier_id = await get_verifier_id_create(
            verification_date=verification_date,
            employee_verifier=default_verifier,
            act_number_entry=act_number_entry,
            verification_limit=verification_limit,
            company_id=company_id,
            company_tz=company_tz,
            session=session
        )

    verification_entry = VerificationEntryModel(
        company_id=company_id, employee_id=employee_id,
        act_number_id=act_number_entry.id, verifier_id=verifier_id,
        equipments=await equipment_repo.get_valid_equipments(verifier_id)
    )

    for field, value in verification_entry_data.model_dump(
        exclude={"act_number", "company_tz"}
    ).items():
        setattr(verification_entry, field, value)

    if verification_entry.verification_result:
        verification_entry.reason_id = None

    session.add(verification_entry)
    await session.flush()

    if verification_entry.location_id:
        await location_repo.increment_count(verification_entry.location_id)

    await increment_verification_count(
        session=session, company_id=company_id, delta=1
    )

    if company_params.yandex_disk_token:
        await session.refresh(
            verification_entry,
            attribute_names=["employee", "series", "act_number"]
        )

        v = verification_entry
        employee = v.employee
        series = v.series
        act_num = v.act_number

        employee_fio = (
            f"{employee.last_name.title()} "
            f"{employee.name.title()} "
            f"{employee.patronymic.title()}"
        )

        await process_act_number_photos(
            session=session,
            act_number_id=v.act_number_id,
            company_name=company_params.name,
            employee_fio=employee_fio,
            verification_date=v.verification_date,
            act_series=series.name,
            act_number=act_num.act_number,
            token=company_params.yandex_disk_token,
            new_images=new_images or [],
            deleted_images_id=verification_entry_data.deleted_images_id or []
        )

    if company_params.auto_metrolog:
        await session.refresh(
            verification_entry,
            attribute_names=[
                "reason", "equipments"
            ]
        )
        is_correct = None
        reason_type = None

        if not verification_entry:
            raise VerificationEntryException

        if not verification_entry.verifier_id:
            raise VerificationVerifierException

        if not verification_entry.equipments:
            raise VerificationEquipmentException

        use_opt_flag = any(e.is_opt for e in verification_entry.equipments)

        if verification_entry.reason:
            if verification_entry.reason.type == ReasonType.p_2_7_3:
                is_correct = False
                reason_type = True
            else:
                is_correct = True
                reason_type = False
        else:
            is_correct = True
            reason_type = True

        metrolog_data = MetrologInfoForm()
        metrolog_data = await right_automatisation_metrolog(
            metrolog_data, water_type=verification_entry.water_type,
            latitude=company_params.latitude,
            longitude=company_params.longitude,
            default_pressure=company_params.default_pressure,
            is_correct=is_correct,
            reason_type=reason_type,
            use_opt=use_opt_flag
        )

        metrolog_info = MetrologInfoModel(
            company_id=company_id,
            verification_id=verification_entry.id
        )

        for key, value in metrolog_data.model_dump().items():
            setattr(metrolog_info, key, value)

        session.add(metrolog_info)
        await session.flush()

        await clear_verification_cache(company_id)

        return {
            "status": "ok",
            "verification_entry_id": verification_entry.id,
            "metrolog_info_id": metrolog_info.id,
            "redirect_to": "p" if redirect_to_metrolog_info else "v"
        }

    await clear_verification_cache(company_id)
    return {
        "status": "ok",
        "verification_entry_id": verification_entry.id,
        "metrolog_info_id": None,
        "redirect_to": "m" if redirect_to_metrolog_info else "v"
    }


@verifications_control_api_router.post("/update")
async def update_verification_entry(
    verification_entry_data: UpdateVerificationEntryForm = Body(...),
    new_images: List[UploadFile] = File(default_factory=list),

    company_id: int = Query(..., ge=1, le=settings.max_int),
    verification_entry_id: int = Query(..., ge=1, le=settings.max_int),
    redirect_to_metrolog_info: bool = Query(...),

    company_tz: str = Depends(get_company_timezone),
    session: AsyncSession = Depends(async_db_session_begin),
    employee_data: JwtData = Depends(
        check_active_access_verification),
    empl_cities_repo: EmployeeCitiesRepository = Depends(
        read_employee_cities_repository
    ),
    company_repo: CompanyRepository = Depends(
        read_company_repository
    ),
    verification_entry_repo: VerificationEntryRepository = Depends(
        action_verification_entry_repository
    ),
    location_repo: LocationRepository = Depends(
        action_location_repository
    ),
    equipment_repo: EquipmentRepository = Depends(
        action_equipment_repository
    )
):
    status = employee_data.status
    employee_id = employee_data.id

    validate_company_timezone(
        verification_entry_data.company_tz,
        company_tz,
        company_id
    )

    new_factory_number = verification_entry_data.factory_number
    new_verification_date = verification_entry_data.verification_date

    company_params = await company_repo.get_company_params()

    if status not in admin_director:
        verif_date_block = company_params.verification_date_block
        if verif_date_block and verif_date_block >= \
                verification_entry_data.verification_date:
            raise CreateVerificationDateBlockException

    exists_factory = await verification_entry_repo.exists_entry_by_factory_num(
        factory_number=new_factory_number,
        verification_date=new_verification_date,
        exclude_entry_id=verification_entry_id,
    )
    if exists_factory:
        raise CreateVerificationFactoryNumBlockException

    verification_entry = await verification_entry_repo.get_to_update(
        verification_entry_id=verification_entry_id,
        status=status,
        employee_id=employee_id
    )
    if not verification_entry:
        raise VerificationEntryException

    if verification_entry.verification_number and \
            status not in admin_director:
        raise UpdateVerificationVerNumBlockException

    employee_cities_id = await empl_cities_repo.get_cities_id(employee_id)
    if employee_cities_id:
        if verification_entry.city_id not in employee_cities_id:
            employee_cities_id.append(verification_entry.city_id)
        if verification_entry_data.city_id and \
                verification_entry_data.city_id not in employee_cities_id:
            raise CreateVerificationCitiesBlockException

    if not verification_entry.verifier:
        CreateVerificationDefaultVerifierException

    old_verifier = verification_entry.verifier

    await check_equip_conditions(
        old_verifier.equipments, company_id=company_id
    )

    last_act_number_id = verification_entry.act_number_id
    if last_act_number_id:
        last_act_number = await session.scalar(
            select(ActNumberModel)
            .where(ActNumberModel.id == last_act_number_id)
            .with_for_update()
        )
        if check_similarity_act_numbers(
            entry_data=verification_entry_data,
            last_act_number=last_act_number,
            company_id=company_id
        ):
            await update_existed_act_number(
                entry_data=verification_entry_data,
                act_number_entry=last_act_number,
                company_id=company_id,
                session=session
            )
        else:
            new_act_number = await act_number_for_update(
                company_id=company_id,
                entry_data=verification_entry_data,
                session=session
            )
            check_act_number_limit(
                act_number_entry=new_act_number
            )
            verification_entry.act_number_id = new_act_number.id

            new_act_number.count -= 1
            last_act_number.count += 1

            still_ref = await session.scalar(
                select(exists().where(
                    VerificationEntryModel.company_id == company_id,
                    VerificationEntryModel.act_number_id == last_act_number.id))
            )
            if not still_ref:
                await session.delete(last_act_number)
    else:
        new_act_number = await act_number_for_update(
            company_id=company_id,
            entry_data=verification_entry_data,
            session=session
        )
        check_act_number_limit(
            act_number_entry=new_act_number
        )

        verification_entry.act_number_id = new_act_number.id
        new_act_number.count -= 1

    await session.refresh(
        verification_entry, attribute_names=["act_number"])

    last_verification_date = verification_entry.verification_date
    new_verification_date = verification_entry_data.verification_date
    is_admin_or_director = status in admin_director

    if company_params.auto_teams:
        verification_limit = company_params.daily_verifier_verif_limit
        if not verification_limit or verification_limit < 0:
            raise CompanyVerificationLimitException

        new_verifier_id = verification_entry.verifier_id
        date_changed = (last_verification_date != new_verification_date)
        verifier_changed = (old_verifier.id != new_verifier_id)
        already_admin_changed = verification_entry.change_verifier_by_admin_or_director or False

        if date_changed and verifier_changed:
            if not already_admin_changed:
                await apply_verifier_log_delta(
                    session=session,
                    verifier_id=old_verifier.id,
                    verification_date=last_verification_date,
                    delta=1,
                    default_daily_limit=verification_limit,
                    company_id=company_id,
                    override_limit_check=is_admin_or_director,
                )
                if is_admin_or_director:
                    verification_entry.change_verifier_by_admin_or_director = True

        elif date_changed and not verifier_changed:
            await apply_verifier_log_delta(
                session=session,
                verifier_id=old_verifier.id,
                verification_date=last_verification_date,
                delta=1,
                default_daily_limit=verification_limit,
                company_id=company_id,
                override_limit_check=is_admin_or_director,
            )
            await apply_verifier_log_delta(
                session=session,
                verifier_id=new_verifier_id,
                verification_date=new_verification_date,
                delta=-1,
                default_daily_limit=verification_limit,
                company_id=company_id,
                override_limit_check=is_admin_or_director,
            )

        elif not date_changed and verifier_changed:
            if not already_admin_changed:
                await apply_verifier_log_delta(
                    session=session,
                    verifier_id=old_verifier.id,
                    verification_date=last_verification_date,
                    delta=1,
                    default_daily_limit=verification_limit,
                    company_id=company_id,
                    override_limit_check=is_admin_or_director
                )

                if is_admin_or_director:
                    verification_entry.change_verifier_by_admin_or_director = True

    if status in admin_director and old_verifier.id != new_verifier_id:
        verification_entry.verifier_id = new_verifier_id
        valid_equipments = await equipment_repo.get_valid_equipments(
            verifier_id=new_verifier_id
        )
        verification_entry.equipments.clear()
        verification_entry.equipments.extend(valid_equipments)

    old_location_id = verification_entry.location_id

    for field, value in verification_entry_data.model_dump(
            exclude={"verifier_id", "act_number", "company_tz"}).items():
        setattr(verification_entry, field, value)

    if verification_entry.verification_result:
        verification_entry.reason_id = None

    new_location_id = verification_entry.location_id
    if old_location_id != new_location_id:
        if old_location_id:
            await location_repo.decrement_count(old_location_id)
        if new_location_id:
            await location_repo.increment_count(new_location_id)

    if company_params.yandex_disk_token:
        await session.refresh(
            verification_entry,
            attribute_names=[
                "employee",
                "series",
                "act_number"
            ]
        )

        v = verification_entry
        employee = v.employee
        series = v.series
        act_num = v.act_number

        employee_fio = (
            f"{employee.last_name.title()} "
            f"{employee.name.title()} "
            f"{employee.patronymic.title()}"
        )

        await process_act_number_photos(
            session=session,
            act_number_id=v.act_number_id,
            company_name=company_params.name,
            employee_fio=employee_fio,
            verification_date=v.verification_date,
            act_series=series.name,
            act_number=act_num.act_number,
            token=company_params.yandex_disk_token,
            new_images=new_images or [],
            deleted_images_id=verification_entry_data.deleted_images_id or []
        )

    if company_params.auto_metrolog:
        await session.refresh(
            verification_entry,
            attribute_names=[
                "reason", "equipments", "metrolog"
            ]
        )
        if not verification_entry:
            raise VerificationEntryException

        if not verification_entry.verifier_id:
            raise VerificationVerifierException

        if not verification_entry.equipments:
            raise VerificationEquipmentException

        use_opt_flag = any(e.is_opt for e in verification_entry.equipments)

        reason = verification_entry.reason
        if reason:
            if reason.type == ReasonType.p_2_7_3:
                is_correct = False
                reason_type = True
            else:
                is_correct = True
                reason_type = False
        else:
            is_correct = True
            reason_type = True

        metrolog_info = verification_entry.metrolog
        if not metrolog_info:
            metrolog_data = MetrologInfoForm()
            metrolog_data = await right_automatisation_metrolog(
                metrolog_data,
                water_type=verification_entry.water_type,
                latitude=company_params.latitude,
                longitude=company_params.longitude,
                default_pressure=company_params.default_pressure,
                is_correct=is_correct,
                reason_type=reason_type,
                use_opt=use_opt_flag
            )
            await session.execute(
                delete(MetrologInfoModel)
                .where(
                    MetrologInfoModel.verification_id == verification_entry.id
                )
            )

            metrolog_info = MetrologInfoModel(
                company_id=company_id,
                verification_id=verification_entry.id
            )

            for key, value in metrolog_data.model_dump().items():
                setattr(metrolog_info, key, value)

            session.add(metrolog_info)
            await session.flush()
            await clear_verification_cache(company_id)

        return {
            "status": "ok",
            "verification_entry_id": verification_entry.id,
            "metrolog_info_id": metrolog_info.id,
            "redirect_to": "p" if redirect_to_metrolog_info else "v"
        }

    await clear_verification_cache(company_id)
    return {
        "status": "ok",
        "verification_entry_id": verification_entry.id,
        "metrolog_info_id": None,
        "redirect_to": "m" if redirect_to_metrolog_info else "v"
    }


@verifications_control_api_router.delete("/delete")
async def delete_verification_entry(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    verification_entry_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(
        check_active_access_verification),
    session: AsyncSession = Depends(async_db_session_begin),
    verification_entry_repo: VerificationEntryRepository = Depends(
        action_verification_entry_repository
    ),
    location_repo: LocationRepository = Depends(
        action_location_repository
    ),
    verification_log_repo: VerificationLogRepository = Depends(
        action_verification_log_repository
    ),
):
    status = user_data.status
    employee_id = user_data.id

    ver_entry = await verification_entry_repo.get_for_delete(
        verification_entry_id=verification_entry_id,
        employee_id=employee_id,
        status=status,
    )

    if not ver_entry:
        raise DeleteVerificationEntryAccessException

    token = ver_entry.company.yandex_disk_token if ver_entry.company else None

    if ver_entry.location_id:
        await location_repo.decrement_count(ver_entry.location_id)

    await verification_entry_repo.delete_related(ver_entry.id)
    await session.flush()

    act_number = ver_entry.act_number
    delete_from_disk = False

    if act_number:
        act_number.count += 1
        if act_number.count >= 4:
            delete_from_disk = True
            await verification_entry_repo.delete_all_with_act(act_number.id)
        else:
            await verification_entry_repo.delete_entry(ver_entry.id)
    else:
        await verification_entry_repo.delete_entry(ver_entry.id)

    verification_log = await verification_log_repo.get_for_update(
        verifier_id=ver_entry.verifier.id,
        verification_date=ver_entry.verification_date,
    )
    if verification_log:
        verification_log.verification_limit += 1

    if delete_from_disk and token:
        employee = ver_entry.verifier
        employee_fio = (
            f"{employee.last_name.title()} "
            f"{employee.name.title()} "
            f"{employee.patronymic.title()}"
        )

        async with get_yandex_service(token) as yandex:
            try:
                await yandex.delete_resource(
                    company_name=ver_entry.company.name,
                    employee_fio=employee_fio,
                    verification_date=ver_entry.verification_date,
                    act_series=ver_entry.series.name,
                    act_number=ver_entry.act_number.act_number,
                    permanently=True
                )
            except HTTPException as e:
                if e.status_code != 404:
                    raise HTTPException(
                        502,
                        detail=f"Ошибка удаления папки на Я.Диске: {e.detail}"
                    )

    await decrement_verification_count(
        session=session,
        company_id=company_id,
        delta=1
    )

    await clear_verification_cache(company_id)
    return Response(status_code=204)
