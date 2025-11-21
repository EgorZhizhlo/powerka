import aiohttp
import asyncio
from datetime import date as date_
from typing import Dict, List, Tuple, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from models import VerificationEntryModel, CompanyModel
from infrastructure.db import async_db_session_begin
from apps.verification_app.schemas.arshin import VriRequestSchema
from access_control import JwtData, auditor_verifier_exception

arshin_router = APIRouter(prefix="/api/arshin")

ARSHIN_BASE_URL = "https://fgis.gost.ru/fundmetrology/eapi"
PAGE_SIZE = 100
RETRIES = 4
AIOHTTP_TIMEOUT = 60
AIOHTTP_LIMIT = 10


async def fetch_page(session, org_title, date_str, start):
    params = {
        "org_title": org_title,
        "verification_date": date_str,
        "start": start,
        "rows": PAGE_SIZE,
    }

    last_exc = None

    for attempt in range(RETRIES):
        try:
            async with session.get("/vri", params=params) as resp:
                if resp.status in (429, 500, 502, 503):
                    await asyncio.sleep(0.2 * (attempt + 1))
                    continue

                resp.raise_for_status()
                return await resp.json()

        except Exception as e:
            last_exc = e
            await asyncio.sleep(0.2 * (attempt + 1))

    raise last_exc


async def process_vri(
    session: aiohttp.ClientSession,
    db: AsyncSession,
    company_id: int,
    date_from: date_,
    date_to: date_,
) -> Dict[str, Any]:

    res = await db.execute(
        select(CompanyModel.name).where(CompanyModel.id == company_id)
    )
    org_title = res.scalar_one()

    res2 = await db.execute(
        select(
            VerificationEntryModel.id,
            VerificationEntryModel.factory_number,
            VerificationEntryModel.verification_date,
        ).where(
            VerificationEntryModel.company_id == company_id,
            VerificationEntryModel.verification_date >= date_from,
            VerificationEntryModel.verification_date <= date_to,
            or_(
                VerificationEntryModel.verification_result.is_(None),
                func.length(
                    func.trim(
                        VerificationEntryModel.verification_result)) == 0,
            ),
        )
    )
    rows: List[Tuple[int, str, date_]] = res2.all()

    by_date: Dict[date_, List[Tuple[int, str]]] = {}
    for vid, fac_no, d in rows:
        if fac_no:
            by_date.setdefault(d, []).append((vid, fac_no.strip()))

    updated = 0
    not_found = 0

    for ver_date, entries in sorted(by_date.items()):
        date_str = ver_date.strftime("%Y-%m-%d")

        wanted: Dict[str, List[int]] = {}
        for entry_id, fac in entries:
            wanted.setdefault(fac, []).append(entry_id)

        remaining = set(wanted.keys())

        start = 0
        total = None

        while True:
            payload = await fetch_page(session, org_title, date_str, start)

            result = payload.get("result") or {}
            items = result.get("items") or []

            if total is None:
                total = result.get("count")

            if not items:
                break

            updates: List[Tuple[int, str]] = []

            for rec in items:
                mi = rec.get("mi_number", "").strip()
                doc = rec.get("result_docnum", "")

                if mi and mi in remaining and doc:
                    for entry_id in wanted[mi]:
                        updates.append((entry_id, doc))
                    remaining.discard(mi)

            if updates:
                id2doc = {item_id: doc for item_id, doc in updates}

                res3 = await db.execute(
                    select(VerificationEntryModel)
                    .where(VerificationEntryModel.id.in_(id2doc.keys()))
                )
                models = res3.scalars().all()

                for m in models:
                    m.verification_result = id2doc[m.id]

                updated += len(updates)

            if not remaining:
                break

            start += PAGE_SIZE
            if total is not None and start >= total:
                break

            await asyncio.sleep(0.05)

        not_found += len(remaining)

    return {
        "updated": updated,
        "not_found": not_found,
        "total": len(rows),
    }


@arshin_router.get("/get-vri-ids")
async def get_vri_ids(
    data: VriRequestSchema = Depends(),
    company_id: int = Query(...),
    db: AsyncSession = Depends(async_db_session_begin),
    user_data: JwtData = Depends(auditor_verifier_exception),
):

    connector = aiohttp.TCPConnector(limit=AIOHTTP_LIMIT)
    timeout = aiohttp.ClientTimeout(total=AIOHTTP_TIMEOUT)

    async with aiohttp.ClientSession(
        base_url=ARSHIN_BASE_URL,
        connector=connector,
        timeout=timeout,
        headers={"Accept": "application/json"}
    ) as session:

        result = await process_vri(
            session=session,
            db=db,
            company_id=company_id,
            date_from=data.date_from,
            date_to=data.date_to,
        )

    return result
