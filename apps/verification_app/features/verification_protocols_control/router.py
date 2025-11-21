from urllib.parse import quote
from io import BytesIO
import zipfile
import asyncio
import os
import threading
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from fastapi.templating import Jinja2Templates

from access_control import (
    JwtData,
    check_access_verification,
    auditor_verifier_exception
)

from core.config import settings
from core.templates.jinja_filters import get_current_date_in_tz
from core.db.dependencies import get_company_timezone
from core.utils.cpu_bounds_runner import run_cpu_bounds_task
from core.exceptions.frontend import (
    FrontendVerificationVerifierError,
    FrontendVerifProtocolAccessError,
    BadRequestError,
)

from apps.verification_app.common import (
    check_equip_conditions, generate_protocol, get_protocol_info
)
from apps.verification_app.repositories import (
    VerificationEntryRepository, read_verification_entry_repository
)
from apps.verification_app.schemas.verification_protocols_control import (
    ReportProtocolsForm
)


verification_protocols_router = APIRouter(
    prefix="/api/verification-protocols"
)
templates = Jinja2Templates(directory="templates/verification")


_zip_generation_locks: dict[int, asyncio.Lock] = {}
_zip_generation_lock = asyncio.Lock()
BATCH_SIZE = 50


def build_filename(
    verification_number: str,
    company_tz: str = "Europe/Moscow"
) -> str:
    ver_number = verification_number or ""
    ver_number = ver_number.rsplit(
        "/", 1)[-1] if "/" in ver_number else ver_number
    current_date = get_current_date_in_tz(company_tz)
    date_str = current_date.strftime("%Y-%m-%d")
    return f"Протокол поверки №{ver_number} от {date_str}.pdf"


@verification_protocols_router.get("/one/")
async def pdf_verification_protocol(
    company_id: int = Query(..., ge=1, le=settings.max_int),
    verification_entry_id: int = Query(..., ge=1, le=settings.max_int),
    metrolog_info_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(
        check_access_verification
    ),
    company_tz: str = Depends(get_company_timezone),
    verification_entry_repo: VerificationEntryRepository = Depends(
        read_verification_entry_repository
    )
):
    status = employee_data.status
    employee_id = employee_data.id

    verification_entry = await verification_entry_repo.get_for_protocol(
        verification_entry_id=verification_entry_id,
        metrolog_info_id=metrolog_info_id,
        employee_id=employee_id,
        status=status
    )

    if not verification_entry:
        raise FrontendVerifProtocolAccessError(company_id=company_id)
    if not verification_entry.verifier_id:
        raise FrontendVerificationVerifierError(company_id=company_id)

    await check_equip_conditions(
        verification_entry.equipments, company_id=company_id
    )

    filename = build_filename(
        verification_entry.verification_number, company_tz
    )

    protocol_info = get_protocol_info(verification_entry)
    buffer: BytesIO = await run_cpu_bounds_task(
        generate_protocol, protocol_info)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f"inline; filename*=utf-8''{quote(filename)}"
            )
        },
    )


@verification_protocols_router.get("/any/zip/")
async def zip_pdf_verifications_protocol(
    protocols_form: ReportProtocolsForm = Depends(),
    company_id: int = Query(..., ge=1, le=settings.max_int),
    employee_data: JwtData = Depends(auditor_verifier_exception),
    company_tz: str = Depends(get_company_timezone),
    verification_entry_repo: VerificationEntryRepository = Depends(
        read_verification_entry_repository
    )
):
    async with _zip_generation_lock:
        lock = _zip_generation_locks.get(company_id)
        if lock is None:
            lock = asyncio.Lock()
            _zip_generation_locks[company_id] = lock

    if lock.locked():
        raise BadRequestError(
            detail="Выгрузка этой компании уже выполняется, попробуйте позже!"
        )

    async def generate_zip_stream():
        try:
            async with lock:
                verification_entries = (
                    await verification_entry_repo.get_for_protocols(
                        date_from=protocols_form.date_from,
                        date_to=protocols_form.date_to,
                        employee_id=protocols_form.employee_id,
                        series_id=protocols_form.series_id,
                    )
                )

                if not verification_entries:
                    empty_zip = BytesIO()
                    with zipfile.ZipFile(
                            empty_zip, "w", zipfile.ZIP_DEFLATED) as zf:
                        zf.writestr("Протоколы_поверки/", "")
                    empty_zip.seek(0)
                    yield empty_zip.getvalue()
                    return

                total_entries = len(verification_entries)

                protocol_infos = [
                    get_protocol_info(
                        entry,
                        any_reports=True,
                        use_opt_status=protocols_form.use_opt_status,
                    )
                    for entry in verification_entries
                ]

                pdf_results = []
                for i in range(0, total_entries, BATCH_SIZE):
                    batch_infos = protocol_infos[i:i + BATCH_SIZE]
                    pdf_tasks = [
                        run_cpu_bounds_task(generate_protocol, info)
                        for info in batch_infos
                    ]
                    pdf_buffers = await asyncio.gather(*pdf_tasks)
                    pdf_results.extend(zip(batch_infos, pdf_buffers))

                r_fd, w_fd = os.pipe()
                r_file = os.fdopen(r_fd, "rb", buffering=0)
                w_file = os.fdopen(w_fd, "wb", buffering=0)

                def writer():
                    try:
                        with zipfile.ZipFile(
                            w_file, mode="w", compression=zipfile.ZIP_STORED
                        ) as zipf:
                            folder_name = "Протоколы_поверки"
                            seen = set()
                            for info, buffer in pdf_results:
                                ver_num = info.get("verification_number", "")
                                filename = build_filename(ver_num, company_tz)
                                base, ext = (
                                    filename.rsplit(".", 1) + [""]
                                )[:2]
                                ext = f".{ext}" if ext else ""
                                name = filename
                                k = 1
                                while name in seen:
                                    name = f"{base} ({k}){ext}"
                                    k += 1
                                seen.add(name)
                                arcname = f"{folder_name}/{name}"
                                zipf.writestr(arcname, buffer.getvalue())
                    except Exception as e:
                        print(f"[ZIP writer error]: {e}")
                    finally:
                        try:
                            w_file.close()
                        except Exception:
                            pass
                threading.Thread(target=writer, daemon=True).start()

                loop = asyncio.get_event_loop()
                try:
                    while True:
                        chunk = await loop.run_in_executor(
                            None, r_file.read, 64 * 1024
                        )
                        if not chunk:
                            break
                        yield chunk
                finally:
                    r_file.close()
        finally:
            if not lock.locked():
                async with _zip_generation_lock:
                    if _zip_generation_locks.get(company_id) is lock:
                        _zip_generation_locks.pop(company_id, None)

    zip_name = "Протоколы_поверки.zip"
    content_disp = f"attachment; filename*=UTF-8''{quote(zip_name)}"
    return StreamingResponse(
        generate_zip_stream(),
        media_type="application/zip",
        headers={"Content-Disposition": content_disp},
    )
