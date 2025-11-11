from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import HTTPException
from models import (
    VerificationLogModel, ActNumberModel)


def check_similarity_act_numbers(
        entry_data, last_act_number, company_id
) -> bool:
    return (
        last_act_number.act_number == entry_data.act_number and
        last_act_number.series_id == entry_data.series_id and
        last_act_number.company_id == company_id
    )


async def update_existed_act_number(
        entry_data,
        act_number_entry: ActNumberModel,
        company_id: int,
        session: AsyncSession
):
    do_not_touch: set[str] = {"company_id", "act_number", "series_id"}

    # Поля, которые реально обновляем
    update_data = entry_data.model_dump(
        exclude_unset=True,
        exclude=do_not_touch
    )
    update_data["company_id"] = company_id

    for field, value in update_data.items():
        setattr(act_number_entry, field, value)
    await session.flush()


async def act_number_for_update(
    company_id: int,
    entry_data,
    session: AsyncSession,
) -> ActNumberModel:
    # Поля, которые не должны меняться при апдейте
    do_not_touch: set[str] = {"company_id", "act_number", "series_id"}

    # Значения ключевых полей для поиска
    act_number_val = entry_data.act_number
    series_id_val = entry_data.series_id

    # Поля, которые реально обновляем
    update_data = entry_data.model_dump(
        exclude_unset=True,
        exclude=do_not_touch
    )
    update_data["company_id"] = company_id

    query = (
        select(ActNumberModel)
        .where(
            ActNumberModel.act_number == act_number_val,
            ActNumberModel.series_id == series_id_val,
            ActNumberModel.company_id == company_id,)
        .with_for_update()
    )
    act_number = await session.scalar(query)

    if not act_number:
        act_number = ActNumberModel(
            act_number=act_number_val,
            series_id=series_id_val,
            company_id=company_id,
        )
        async with session.begin_nested():
            session.add(act_number)
            try:
                await session.flush()
            except IntegrityError:
                await session.rollback()

        act_number = await session.scalar(query)

    for field, value in update_data.items():
        setattr(act_number, field, value)

    await session.flush()
    await session.refresh(act_number)
    return act_number


async def check_act_number_limit(
    act_number_entry: ActNumberModel,
) -> None:
    if not act_number_entry:
        raise HTTPException(
            status_code=404,
            detail="Запись номера акта не была найдена."
        )

    if act_number_entry.count <= 0:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Лимит записей по номеру акта: "
                f"{act_number_entry.act_number} превышен."
            )
        )


async def get_verification_log_of_verifier(
    verification_date,
    verification_limit: int,
    verifier_id: int,
    session: AsyncSession,
) -> VerificationLogModel:
    # Забираем уже существующие логи и блокируем их
    query = (
        select(VerificationLogModel)
        .where(
            VerificationLogModel.verifier_id == verifier_id,
            VerificationLogModel.verification_date == verification_date,
        )
        .with_for_update()
    )
    verification_log = await session.scalar(query)
    if verification_log:
        return verification_log

    created = None
    async with session.begin_nested():
        created = VerificationLogModel(
            verification_limit=verification_limit,
            verification_date=verification_date,
            verifier_id=verifier_id,
        )
        session.add(created)
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            created = None

    if created is not None:
        return created

    # Кто-то создал параллельно — перечитываем под блокировку
    verification_log = await session.scalar(query)
    if verification_log is None:
        # На случай крайне редкой гонки — повторим создание
        async with session.begin_nested():
            verification_log = VerificationLogModel(
                verification_limit=verification_limit,
                verification_date=verification_date,
                verifier_id=verifier_id,
            )
            session.add(verification_log)
            await session.flush()
        return verification_log

    return verification_log


async def true_false_access_to_create_entry_with_this_verifier(
    verification_log: VerificationLogModel,
) -> bool:
    if verification_log.verification_limit - 1 < -3:
        return False
    return True


async def apply_verifier_log_delta(
    *,
    session: AsyncSession,
    verifier_id: int,
    verification_date,
    delta: int,
    default_daily_limit: int,
    override_limit_check: bool = False,
) -> None:
    log = await get_verification_log_of_verifier(
        verification_date=verification_date,
        verification_limit=default_daily_limit,
        verifier_id=verifier_id,
        session=session,
    )

    if delta < 0 and not override_limit_check:
        if not await true_false_access_to_create_entry_with_this_verifier(log):
            raise HTTPException(
                status_code=409,
                detail="Лимит поверок у выбранного поверителя на указанную дату исчерпан.",
            )

    # Применяем изменение всегда (для админа/директора — без блокирующей проверки)
    log.verification_limit = (log.verification_limit or 0) + delta
    await session.flush()
