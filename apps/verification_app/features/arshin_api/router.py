import aiohttp
import asyncio
import ssl
import re
from datetime import date as date_
from typing import Optional, Dict, List, Tuple, Any
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import select, func, or_

from models import VerificationEntryModel, CompanyModel
from access_control import JwtData, auditor_verifier_exception
from core.config import settings
from infrastructure.db import async_session_maker
from apps.verification_app.schemas.arshin import VriRequestSchema


arshin_router = APIRouter(prefix="/api/arshin")
ARSHIN_BASE_URL = "https://fgis.gost.ru/fundmetrology/eapi"
ARSHIN_ROWS_LIMIT = 100
AIOHTTP_TIMEOUT = 60
AIOHTTP_LIMIT = 20
AIOHTTP_RETRIES = 5

_NORMALIZE_RE = re.compile(r"[№#\s]+")


def _normalize_factory_number(s: str) -> str:
    if not s:
        return ""
    return _NORMALIZE_RE.sub("", s).upper()


async def _fetch_arshin_page(
    session: aiohttp.ClientSession,
    org_title: str,
    date_str: str,
    start: int,
) -> Dict[str, Any]:

    params = {
        "org_title": org_title,
        "verification_date": date_str,
        "rows": ARSHIN_ROWS_LIMIT,
        "start": start,
    }

    for attempt in range(AIOHTTP_RETRIES):
        try:
            async with session.get("/vri", params=params) as resp:

                # повторяем при 429, 500, 502, 503
                if resp.status in (429, 500, 502, 503):
                    await asyncio.sleep(0.3 * (attempt + 1))
                    continue

                resp.raise_for_status()
                return await resp.json()

        except Exception:
            if attempt == AIOHTTP_RETRIES - 1:
                raise
            await asyncio.sleep(0.2 * (attempt + 1))

    return {}


async def _background_fill_vri_ids(
    company_id: int,
    date_from: date_,
    date_to: date_,
) -> None:

    # Получаем данные
    async with async_session_maker() as db_read:
        res_company = await db_read.execute(
            select(CompanyModel.name).where(CompanyModel.id == company_id)
        )
        company_name = res_company.scalar_one()

        res_entries = await db_read.execute(
            select(
                VerificationEntryModel.id,
                VerificationEntryModel.factory_number,
                VerificationEntryModel.verification_date,
            ).where(
                VerificationEntryModel.company_id == company_id,
                VerificationEntryModel.verification_date >= date_from,
                VerificationEntryModel.verification_date <= date_to,
                or_(
                    VerificationEntryModel.verification_number.is_(None),
                    func.length(func.trim(VerificationEntryModel.verification_number)) == 0,
                ),
            )
        )
        rows: List[Tuple[int, str, date_]] = res_entries.all()

    by_date: Dict[date_, List[Tuple[int, str]]] = {}
    for ver_id, fac_no, ver_date in rows:
        by_date.setdefault(ver_date, []).append((ver_id, fac_no))

    dates_sorted = sorted(by_date.keys())
    org_title_lower = (company_name or "")

    # Настраиваем SSL
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    # Создаём AIOHTTP
    connector = aiohttp.TCPConnector(
        limit=AIOHTTP_LIMIT,
        ssl=ssl_ctx
    )

    timeout = aiohttp.ClientTimeout(total=AIOHTTP_TIMEOUT)

    async with aiohttp.ClientSession(
        base_url=ARSHIN_BASE_URL,
        timeout=timeout,
        connector=connector,
        headers={"Accept": "application/json"}
    ) as session:

        # Основной цикл
        for cur_date in dates_sorted:
            target_entries = by_date[cur_date]

            # карта normalized → entry_ids
            needed_map: Dict[str, List[int]] = {}

            for entry_id, fac_no in target_entries:
                mi_norm = _normalize_factory_number(fac_no)
                if mi_norm:
                    needed_map.setdefault(mi_norm, []).append(entry_id)

            if not needed_map:
                continue

            remaining = set(needed_map.keys())
            date_label = cur_date.strftime("%d.%m.%Y")

            start = 0
            total: Optional[int] = None

            # цикл пагинации Аршина
            while True:

                payload = await _fetch_arshin_page(
                    session=session,
                    org_title_lower=org_title_lower,
                    date_ddmmyyyy=date_label,
                    start=start,
                )

                result = payload.get("result") or {}
                items = result.get("items") or []
                total = result.get("count") if total is None else total

                if not items:
                    break

                updates: List[Tuple[int, Optional[str]]] = []

                # сопоставление
                for rec in items:
                    mi_raw = rec.get("mi_number") or ""
                    mi_norm = _normalize_factory_number(mi_raw)

                    if mi_norm in remaining:
                        vri_id = rec.get("vri_id")

                        for ver_entry_id in needed_map.get(mi_norm, []):
                            updates.append(
                                (ver_entry_id, str(vri_id) if vri_id else None)
                            )

                        remaining.discard(mi_norm)

                # запись в БД
                if updates:
                    async with async_session_maker() as db_write:
                        async with db_write.begin():
                            ids = [u[0] for u in updates]

                            res_models = await db_write.execute(
                                select(VerificationEntryModel)
                                .where(VerificationEntryModel.id.in_(ids))
                            )
                            models = res_models.scalars().all()

                            id2vri = {u[0]: u[1] for u in updates}

                            for m in models:
                                m.verification_number = id2vri[m.id]

                if not remaining:
                    break

                start += ARSHIN_ROWS_LIMIT

                if total is not None and start >= int(total):
                    break

                await asyncio.sleep(0.03)


@arshin_router.get("/get-vri-ids", status_code=204)
async def get_vri_ids(
    background_tasks: BackgroundTasks,
    data: VriRequestSchema = Depends(),
    company_id: int = Query(..., ge=1, le=settings.max_int),
    user_data: JwtData = Depends(auditor_verifier_exception),
):
    background_tasks.add_task(
        _background_fill_vri_ids,
        company_id,
        data.date_from,
        data.date_to
    )
