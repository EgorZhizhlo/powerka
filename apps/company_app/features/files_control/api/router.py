import pandas as pd
from io import BytesIO
from fastapi import (
    APIRouter, Response, UploadFile, Depends, Form, Query,
    status as status_code)
from fastapi.responses import StreamingResponse

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.exceptions.api.common import BadRequestError

from infrastructure.db import async_db_session_begin
from models import (
    MethodModel, SiModificationModel, RegistryNumberModel)

from access_control import (
    JwtData, check_include_in_active_company)


files_control_api_router = APIRouter(
    prefix="/api/files-control"
)


@files_control_api_router.post("/upload")
async def api_upload_file(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    file: UploadFile = Form(...),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    # Проверяем расширение
    allowed_extensions = {"csv", "xlsx", "xls"}
    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in allowed_extensions:
        raise BadRequestError(
            detail="Только .csv, .xlsx и .xls файлы разрешены!"
        )

    # Открываем файл
    try:
        if ext == "csv":
            df = pd.read_csv(file.file, encoding="utf-8", sep=";")
        else:
            xls = pd.ExcelFile(file.file)
            df = xls.parse(xls.sheet_names[0])
    except Exception as e:
        raise BadRequestError(
            detail=f"Ошибка чтения файла: {e}"
        )

    for row in df.to_dict(orient="records"):
        registry_number = row.get('№гос.реестра').strip()
        si_type = row.get('Тип си').strip()
        mpi_hot = int(row.get('МПИ для горячей', 0))
        mpi_cold = int(row.get('МПИ для холодной', 0))
        method_name = str(row.get("Методика поверки", "")).strip()

        # Метод
        method = (await session.execute(
            select(MethodModel)
            .where(
                func.lower(MethodModel.name) == method_name.lower(),
                MethodModel.company_id == company_id)
        )).scalar_one_or_none()
        if not method:
            method = MethodModel(name=method_name, company_id=company_id)
            session.add(method)
            await session.flush()

        # Модификации
        raw_mods = row.get("Модификации СИ") or ""
        mods_list = []
        for name in raw_mods.split(";"):
            name = name.strip()
            if not name:
                continue
            mod = (await session.execute(
                select(SiModificationModel)
                .where(
                    func.lower(
                        SiModificationModel.modification_name) == name.lower(),
                    SiModificationModel.company_id == company_id)
            )).scalar_one_or_none()
            if not mod:
                mod = SiModificationModel(
                    company_id=company_id, modification_name=name)
                session.add(mod)
                await session.flush()
            mods_list.append(mod)

        # Проверяем существующий реестр
        existing = (await session.execute(
            select(RegistryNumberModel)
            .where(
                func.lower(
                    RegistryNumberModel.registry_number
                ) == registry_number.lower(),
                RegistryNumberModel.company_id == company_id)
            .options(
                selectinload(RegistryNumberModel.method),
                selectinload(RegistryNumberModel.modifications))
        )).scalar_one_or_none()

        if existing:
            # Обновляем все поля, включая список модификаций
            existing.si_type = si_type
            existing.mpi_hot = mpi_hot
            existing.mpi_cold = mpi_cold
            existing.method_id = method.id
            existing.modifications = mods_list
            existing.registry_number = registry_number
        else:
            # Создаём новую запись с модификациями
            new_rec = RegistryNumberModel(
                company_id=company_id,
                registry_number=registry_number,
                si_type=si_type,
                mpi_hot=mpi_hot,
                mpi_cold=mpi_cold,
                method_id=method.id,
                modifications=mods_list
            )
            session.add(new_rec)

    return Response(status_code=status_code.HTTP_204_NO_CONTENT)


@files_control_api_router.get("/download")
async def api_download_file(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(check_include_in_active_company),
    session: AsyncSession = Depends(async_db_session_begin),
):
    data = (await session.execute(
        select(RegistryNumberModel)
        .options(
            selectinload(RegistryNumberModel.method),
            selectinload(RegistryNumberModel.modifications))
        .where(RegistryNumberModel.company_id == company_id)
    )).scalars().all()

    records = [
        {
            "№гос.реестра": item.registry_number,
            "Тип си": item.si_type,
            "МПИ для горячей": item.mpi_hot,
            "МПИ для холодной": item.mpi_cold,
            "Методика поверки": item.method.name if item.method else "",
            "Модификации СИ": ";".join(
                mod.modification_name for mod in item.modifications)
        }
        for item in data
    ]

    df = pd.DataFrame(records)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats"
        "-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; "
            "filename=GosReestr_CTC.xlsx"
        }
    )
