from datetime import date as date_

from sqlalchemy import func, text, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from models import RouteStatisticModel, RouteModel


def _advisory_key(
        route_id: int, d: date_) -> int:
    # стабильный 64-битный ключ
    return (route_id << 32) | int(d.strftime("%Y%m%d"))


async def lock_routes_advisory(
        session: AsyncSession, route_ids: list[int], d: date_) -> None:
    for rid in sorted(set(route_ids)):
        key = _advisory_key(rid, d)
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})


async def _upsert_route_stat(
        session: AsyncSession, route_id: int, d: date_,
        day_limit: int) -> None:
    """
    Гарантируем, что запись существует. Если есть — не ломаем текущее значение,
    но держим его в допустимых рамках [0..day_limit].
    Требуется UNIQUE(route_id, date) на route_statistic (у тебя он есть).
    """
    stmt = (
        pg_insert(RouteStatisticModel.__table__)
        .values(route_id=route_id, date=d, day_limit_free=day_limit)
        .on_conflict_do_update(
            index_elements=[
                RouteStatisticModel.route_id,
                RouteStatisticModel.date
            ],
            set_={
                "day_limit_free": func.least(
                    func.greatest(RouteStatisticModel.day_limit_free, 0),
                    day_limit,
                ),
                "updated_at": func.now(),
            },
        )
    )
    await session.execute(stmt)


async def _change_slot(
    session: AsyncSession,
    route_id: int,
    d: date_,
    delta: int,
    day_limit: int,
) -> None:
    """
    Атомно изменяет day_limit_free на +-1 с защитой от выхода за границы.
    Требует, чтобы снаружи был взят advisory-lock для (route_id, d).
    """

    await _upsert_route_stat(session, route_id, d, day_limit)

    if delta < 0:
        # Резервирование: уменьшаем, только если есть свободные места
        updated = await session.execute(
            update(RouteStatisticModel)
            .where(
                RouteStatisticModel.route_id == route_id,
                RouteStatisticModel.date == d,
                RouteStatisticModel.day_limit_free > 0,
            )
            .values(
                day_limit_free=RouteStatisticModel.day_limit_free - 1,
            )
            .returning(RouteStatisticModel.day_limit_free)
        )
        result = updated.scalar_one_or_none()
        if result is None:
            raise ValueError(
                f"Нет свободных мест (route_id={route_id}, date={d})")
    else:
        await session.execute(
            update(RouteStatisticModel)
            .where(
                RouteStatisticModel.route_id == route_id,
                RouteStatisticModel.date == d,
                RouteStatisticModel.day_limit_free < day_limit,
            )
            .values(
                day_limit_free=RouteStatisticModel.day_limit_free + 1,
            )
        )


async def get_or_create_route_statistic(
    db: AsyncSession,
    route_id: int,
    date: date_,
    day_limit: int | None = None,
) -> RouteStatisticModel:
    """Создаёт или возвращает запись статистики маршрута."""

    if day_limit is None:
        day_limit = await db.scalar(
            select(RouteModel.day_limit).where(RouteModel.id == route_id)
        )
        if day_limit is None:
            raise ValueError(f"Маршрут {route_id} не найден")

    await _upsert_route_stat(db, route_id, date, day_limit)
    return await db.scalar(
        select(RouteStatisticModel).where(
            RouteStatisticModel.route_id == route_id,
            RouteStatisticModel.date == date,
        )
    )


async def reserve_slot(
    db: AsyncSession,
    route_id: int,
    date: date_,
    day_limit: int | None = None,
) -> RouteStatisticModel:
    """
    Резервирует одно место.
    Бросает ValueError, если нет свободных мест.
    """

    if day_limit is None:
        day_limit = await db.scalar(
            select(RouteModel.day_limit).where(RouteModel.id == route_id)
        )
    if day_limit is None:
        raise ValueError(f"Маршрут {route_id} не найден")

    await _change_slot(db, route_id, date, delta=-1, day_limit=day_limit)

    return await db.scalar(
        select(RouteStatisticModel).where(
            RouteStatisticModel.route_id == route_id,
            RouteStatisticModel.date == date,
        )
    )


async def release_slot(
    db: AsyncSession,
    route_id: int,
    date: date_,
    day_limit: int | None = None,
) -> RouteStatisticModel:
    """
    Освобождает одно место (не больше day_limit).
    """

    if day_limit is None:
        day_limit = await db.scalar(
            select(RouteModel.day_limit).where(RouteModel.id == route_id)
        )
    if day_limit is None:
        raise ValueError(f"Маршрут {route_id} не найден")

    await _change_slot(db, route_id, date, delta=+1, day_limit=day_limit)
    return await db.scalar(
        select(RouteStatisticModel).where(
            RouteStatisticModel.route_id == route_id,
            RouteStatisticModel.date == date,
        )
    )
