import re
import math
from fastapi import (
    APIRouter, Response, status as status_code,
    Depends, Query, Body
)
from sqlalchemy import select, delete, or_, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from asyncpg.exceptions import (
    UniqueViolationError as PGUniqueViolationError,
    NotNullViolationError as PGNotNullViolationError)
from werkzeug.security import generate_password_hash

from access_control import (
    JwtData,
    check_include_in_not_active_company,
    check_include_in_active_company,
    bump_jwt_token_version,
)

from core.config import settings
from core.db.dependencies import get_company_timezone
from core.exceptions import CustomHTTPException, check_is_none
from core.templates.jinja_filters import format_datetime_tz

from infrastructure.db import async_db_session, async_db_session_begin

from models import (
    ActSeriesModel, EmployeeModel, CompanyModel, CityModel, VerifierModel,
    RouteModel
)
from models.associations import employees_routes, employees_cities
from models.enums import EmployeeStatus

from apps.company_app.common import (
    validate_image,
    check_employee_limit_available,
    increment_employee_count,
    decrement_employee_count
)
from apps.company_app.schemas.employees import (
    EmployeesPage, EmployeeOut, EmployeeCreate
)


employees_api_router = APIRouter(
    prefix="/api/employees"
)


@employees_api_router.get("/", response_model=EmployeesPage)
async def api_get_employees(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    page: int = Query(1, ge=1, le=settings.max_int),
    search: str = Query(""),
    session: AsyncSession = Depends(async_db_session),
    user_data: JwtData = Depends(
        check_include_in_not_active_company),
    company_tz: str = Depends(get_company_timezone),
):
    status = user_data.status

    per_page = settings.entries_per_page
    clause = or_(
        EmployeeModel.last_name.ilike(f"%{search}%"),
        EmployeeModel.name.ilike(f"%{search}%"),
        EmployeeModel.patronymic.ilike(f"%{search}%"),
        EmployeeModel.email.ilike(f"%{search}%")
    )

    filters = [
        EmployeeModel.companies.any(CompanyModel.id == company_id),
        clause
    ]

    if status == EmployeeStatus.director:
        filters.append(
            or_(
                EmployeeModel.status.notin_(settings.ADMIN_DIRECTOR),
                EmployeeModel.id == user_data.id  # позволяем видеть себя
            )
        )

    total = (await session.execute(
        select(func.count(EmployeeModel.id))
        .where(*filters)
    )).scalar_one()

    total_pages = max(1, math.ceil(total / per_page))
    page = min(page, total_pages)
    offset = (page - 1) * per_page

    q = (
        select(EmployeeModel)
        .where(*filters)
        .order_by(
            EmployeeModel.is_deleted.isnot(True).desc(),
            EmployeeModel.id.desc()
        )
        .options(
            selectinload(EmployeeModel.default_verifier).load_only(
                VerifierModel.last_name,
                VerifierModel.name,
                VerifierModel.patronymic,
            ), selectinload(EmployeeModel.default_city).load_only(
                CityModel.name
            ), selectinload(EmployeeModel.series).load_only(
                ActSeriesModel.name)
        )
        .limit(per_page)
        .offset(offset)
    )

    employees = (await session.execute(q)).scalars().all()

    result: list[EmployeeOut] = []
    for e in employees:
        e.is_deleted = bool(e.is_deleted)
        out = EmployeeOut.model_validate(e)
        out.has_image = bool(e.image)

        if e.last_login:
            out.last_login_strftime_full = format_datetime_tz(
                e.last_login, company_tz, "%d.%m.%Y %H:%M"
            )
        if e.created_at:
            out.created_at_strftime_full = format_datetime_tz(
                e.created_at, company_tz, "%d.%m.%Y %H:%M"
            )
        if e.updated_at:
            out.updated_at_strftime_full = format_datetime_tz(
                e.updated_at, company_tz, "%d.%m.%Y %H:%M"
            )

        if e.default_verifier:
            out.default_verifier_fullname = (
                f"{
                    e.default_verifier.last_name} {
                        e.default_verifier.name} {
                            e.default_verifier.patronymic}"
            )
        if e.default_city:
            out.default_city_name = e.default_city.name
        if e.series:
            out.series_name = e.series.name
        result.append(out)

    return {"items": result, "page": page, "total_pages": total_pages}


@employees_api_router.get("/image", response_class=Response)
async def api_get_employee_image(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_id: int = Query(..., ge=1, le=settings.max_int),
    session: AsyncSession = Depends(async_db_session),
    user_data: JwtData = Depends(check_include_in_not_active_company)
):
    employee = (await session.execute(
        select(EmployeeModel)
        .where(EmployeeModel.id == employee_id)
        .where(
            EmployeeModel.companies.any(
                CompanyModel.id == company_id
            )
        )
    )).scalar_one_or_none()

    if not employee or not employee.image:
        raise CustomHTTPException(
            company_id=company_id, status_code=404, detail="Фото не найдено"
        )

    return Response(content=employee.image, media_type="image/jpeg")


@employees_api_router.post("/create")
async def api_create_employee(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: EmployeeCreate = Body(...),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    status = user_data.status
    if status == EmployeeStatus.director:
        allowed_statuses = {
            EmployeeStatus.auditor, EmployeeStatus.dispatcher1,
            EmployeeStatus.dispatcher2, EmployeeStatus.verifier
        }
    else:
        allowed_statuses = {
            EmployeeStatus.admin, EmployeeStatus.director,
            EmployeeStatus.auditor, EmployeeStatus.dispatcher1,
            EmployeeStatus.dispatcher2, EmployeeStatus.verifier
        }
    if employee_data.status not in allowed_statuses:
        raise CustomHTTPException(
            company_id=company_id,
            status_code=400,
            detail="Вы использовали несуществующую или недоступную для вас роль сотрудника."
        )

    await check_employee_limit_available(session, company_id, required_slots=1)

    if employee_data.image:
        validate_image(company_id, employee_data.image)

    new_employee = EmployeeModel()
    for field, value in employee_data.model_dump(
        exclude={"password", "city_ids", "route_ids"}
    ).items():
        setattr(new_employee, field, value)

    if employee_data.city_ids:
        rows = await session.execute(
            select(CityModel).where(CityModel.id.in_(employee_data.city_ids))
        )
        new_employee.cities.extend(rows.scalars().all())

    if employee_data.route_ids:
        rows = await session.execute(
            select(RouteModel).where(
                RouteModel.id.in_(employee_data.route_ids))
        )
        new_employee.routes.extend(rows.scalars().all())

    # Связываем с компанией
    company = (await session.execute(
        select(CompanyModel).where(CompanyModel.id == company_id)
    )).scalar_one_or_none()
    new_employee.companies.append(company)

    if employee_data.password:
        new_employee.password = generate_password_hash(employee_data.password)

    try:
        session.add(new_employee)
        await session.flush()

        await increment_employee_count(session, company_id, delta=1)

    except IntegrityError as e:
        # транзакция откатится автоматически
        orig = getattr(e, "orig", None) or getattr(e, "__cause__", None)
        constraint = None
        column = None
        text = ""

        if isinstance(orig, PGUniqueViolationError):
            constraint = getattr(orig, "constraint_name", None)
        elif isinstance(orig, PGNotNullViolationError):
            column = getattr(orig, "column_name", None)
        else:
            text = str(orig or e)
            if "duplicate key value violates unique constraint" in text:
                if "employees_email_key" in text:
                    constraint = "employees_email_key"
                elif "employees_username_key" in text:
                    constraint = "employees_username_key"
            elif "null value in column" in text:
                m = re.search(r'null value in column "([^"]+)"', text)
                if m:
                    column = m.group(1)

        if constraint == "employees_email_key":
            detail = "Пользователь с таким email уже существует."
        elif constraint == "employees_username_key":
            detail = "Пользователь с таким username уже существует."
        elif column == "password":
            detail = "Поле «пароль» не может быть пустым."
        else:
            detail = f"Ошибка БД: {constraint or column or text}"

        raise CustomHTTPException(
            company_id=company_id, status_code=400, detail=detail)

    except Exception as ex:
        raise CustomHTTPException(
            company_id=company_id, status_code=404, detail=str(ex))

    await bump_jwt_token_version(f"user:{new_employee.id}:auth_version")

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@employees_api_router.put("/update")
async def api_update_employee(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: EmployeeCreate = Body(...),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    status = user_data.status
    user_id = user_data.id

    employee = (
        await session.execute(
            select(EmployeeModel)
            .where(
                EmployeeModel.id == employee_id,
                EmployeeModel.companies.any(CompanyModel.id == company_id)
            )
        )
    ).scalar_one_or_none()

    await check_is_none(
        employee, type="Сотрудник", id=employee_id, company_id=company_id
    )

    if status == EmployeeStatus.director:
        if user_id != employee.id:
            allowed_statuses = {
                EmployeeStatus.auditor, EmployeeStatus.dispatcher1,
                EmployeeStatus.dispatcher2, EmployeeStatus.verifier
            }
        else:
            allowed_statuses = {
                EmployeeStatus.director, EmployeeStatus.auditor,
                EmployeeStatus.dispatcher1, EmployeeStatus.dispatcher2,
                EmployeeStatus.verifier
            }
    else:
        allowed_statuses = {
            EmployeeStatus.admin, EmployeeStatus.director,
            EmployeeStatus.auditor, EmployeeStatus.dispatcher1,
            EmployeeStatus.dispatcher2, EmployeeStatus.verifier
        }

    if employee.status not in allowed_statuses:
        raise CustomHTTPException(
            company_id=company_id,
            status_code=400,
            detail="В доступе к сотруднику отказано."
        )

    if employee_data.status not in allowed_statuses:
        raise CustomHTTPException(
            company_id=company_id,
            status_code=400,
            detail="Вы использовали недоступную или неизвестную роль."
        )

    try:
        if employee_data.image:
            validate_image(company_id, employee_data.image)
            employee.image = employee_data.image

        for field, value in employee_data.model_dump(
            exclude={"password", "city_ids", "route_ids", "image"}
        ).items():
            setattr(employee, field, value)

        await session.execute(
            delete(employees_cities)
            .where(employees_cities.c.employee_id == employee.id)
        )
        if employee_data.city_ids:
            cities = (
                await session.execute(
                    select(CityModel).where(
                        CityModel.id.in_(employee_data.city_ids))
                )
            ).scalars().all()
            employee.cities.extend(cities)

        await session.execute(
            delete(employees_routes)
            .where(employees_routes.c.employee_id == employee.id)
        )
        if employee_data.route_ids:
            routes = (
                await session.execute(
                    select(RouteModel).where(
                        RouteModel.id.in_(employee_data.route_ids))
                )
            ).scalars().all()
            employee.routes.extend(routes)

        if employee_data.password:
            employee.password = generate_password_hash(
                employee_data.password)

    except IntegrityError as e:
        # транзакция откатится сама
        orig = getattr(e, "orig", None) or getattr(e, "__cause__", None)
        constraint = None
        column = None

        if isinstance(orig, PGUniqueViolationError):
            constraint = getattr(orig, "constraint_name", None)
        elif isinstance(orig, PGNotNullViolationError):
            column = getattr(orig, "column_name", None)
        else:
            text = str(orig or e)
            if "duplicate key value violates unique constraint" in text:
                if "employees_email_key" in text:
                    constraint = "employees_email_key"
                elif "employees_username_key" in text:
                    constraint = "employees_username_key"
            elif "null value in column" in text:
                m = re.search(r'null value in column "([^"]+)"', text)
                if m:
                    column = m.group(1)

        if constraint == "employees_email_key":
            detail = "Пользователь с таким email уже существует."
        elif constraint == "employees_username_key":
            detail = "Пользователь с таким username уже существует."
        elif constraint:
            detail = f"Нарушено уникальное ограничение: {constraint}"
        elif column:
            detail = ("Поле «пароль» не может быть пустым." if column == "password"
                      else f"Поле «{column}» не может быть пустым.")
        else:
            detail = "Ошибка БД: " + str(e)

        raise CustomHTTPException(
            company_id=company_id, status_code=400, detail=detail)

    except Exception as ex:
        raise CustomHTTPException(
            company_id=company_id, status_code=404, detail=str(ex))

    await bump_jwt_token_version(f"user:{employee.id}:auth_version")

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@employees_api_router.delete("/delete", status_code=204)
async def api_delete_employee(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_id: int = Query(..., ge=1, le=settings.max_int),
    session: AsyncSession = Depends(async_db_session_begin),
    user_data: JwtData = Depends(check_include_in_active_company),
):
    status = user_data.status
    user_id = user_data.id

    employee = (await session.execute(
        select(EmployeeModel)
        .where(EmployeeModel.id == employee_id,
               EmployeeModel.companies.any(CompanyModel.id == company_id),
               EmployeeModel.is_deleted.isnot(True))
        .options(
            selectinload(EmployeeModel.verifications),
            selectinload(EmployeeModel.order),
            selectinload(EmployeeModel.appeal),
            selectinload(EmployeeModel.assignments),
            selectinload(EmployeeModel.cities),
            selectinload(EmployeeModel.routes)
        )
    )).scalar_one_or_none()

    await check_is_none(
        employee, type="Сотрудник", id=employee_id, company_id=company_id
    )

    if status == EmployeeStatus.director:
        if user_id != employee.id:
            allowed_statuses = {
                EmployeeStatus.auditor, EmployeeStatus.dispatcher1,
                EmployeeStatus.dispatcher2, EmployeeStatus.verifier
            }
        else:
            allowed_statuses = {
                EmployeeStatus.director, EmployeeStatus.auditor,
                EmployeeStatus.dispatcher1, EmployeeStatus.dispatcher2,
                EmployeeStatus.verifier
            }
    else:
        allowed_statuses = {
            EmployeeStatus.admin, EmployeeStatus.director,
            EmployeeStatus.auditor, EmployeeStatus.dispatcher1,
            EmployeeStatus.dispatcher2, EmployeeStatus.verifier
        }

    if employee.status not in allowed_statuses:
        raise CustomHTTPException(
            company_id=company_id, status_code=404,
            detail="В доступе к сотруднику отказано."
        )

    has_links = bool(
        employee.verifications or employee.order or employee.appeal or
        employee.assignments
    )

    if has_links:
        employee.is_active = False
        employee.is_deleted = True
        employee.cities.clear()
        employee.routes.clear()
    else:
        await session.delete(employee)

    await decrement_employee_count(session, company_id, delta=1)

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@employees_api_router.post("/restore", status_code=200)
async def api_restore_employee(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_id: int = Query(..., ge=1, le=settings.max_int),
    session: AsyncSession = Depends(async_db_session_begin),
    user_data: JwtData = Depends(check_include_in_active_company),
):
    status = user_data.status
    user_id = user_data.id

    employee = (await session.execute(
        select(EmployeeModel)
        .where(
            EmployeeModel.id == employee_id,
            EmployeeModel.companies.any(CompanyModel.id == company_id),
            EmployeeModel.is_deleted.is_(True))
    )).scalar_one_or_none()

    await check_is_none(
        employee, type="Сотрудник", id=employee_id, company_id=company_id
    )

    if status == EmployeeStatus.director:
        if user_id != employee.id:
            allowed_statuses = {
                EmployeeStatus.auditor, EmployeeStatus.dispatcher1,
                EmployeeStatus.dispatcher2, EmployeeStatus.verifier
            }
        else:
            allowed_statuses = {
                EmployeeStatus.director, EmployeeStatus.auditor,
                EmployeeStatus.dispatcher1, EmployeeStatus.dispatcher2,
                EmployeeStatus.verifier
            }
    else:
        allowed_statuses = {
            EmployeeStatus.admin, EmployeeStatus.director,
            EmployeeStatus.auditor, EmployeeStatus.dispatcher1,
            EmployeeStatus.dispatcher2, EmployeeStatus.verifier
        }

    if employee.status not in allowed_statuses:
        raise CustomHTTPException(
            company_id=company_id, status_code=404,
            detail="В доступе к сотруднику отказано."
        )

    await check_employee_limit_available(session, company_id, required_slots=1)

    employee.is_active = True
    employee.is_deleted = False

    await increment_employee_count(session, company_id, delta=1)

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)
