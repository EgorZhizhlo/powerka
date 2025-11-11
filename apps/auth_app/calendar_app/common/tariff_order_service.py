from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import CustomHTTPException
from models import CompanyTariffState
from apps.tariff_app.services.tariff_cache_service import tariff_cache


async def check_order_limit_available(
    session: AsyncSession,
    company_id: int,
    required_slots: int = 1
) -> None:
    # Быстрая проверка по кешу
    cached_limits = await tariff_cache.get_cached_limits(company_id)

    if cached_limits and cached_limits.get('has_tariff'):
        limits = cached_limits.get('limits', {})
        max_orders = limits.get('max_orders')
        used_orders = limits.get('used_orders', 0)

        # Если безлимит (None) - сразу пропускаем
        if max_orders is None:
            return

        # Если лимит 0 - сразу отказываем
        if max_orders == 0:
            raise CustomHTTPException(
                status_code=403,
                company_id=company_id,
                detail=(
                    "Тарифный план не позволяет создавать заявки. "
                    "Обновите тариф для доступа к функционалу."
                )
            )

        # Если очевидно превышен лимит - отказываем без обращения к БД
        if used_orders + required_slots > max_orders:
            raise CustomHTTPException(
                status_code=403,
                company_id=company_id,
                detail=(
                    f"Превышен лимит заявок ({used_orders}/{max_orders}). "
                    f"Требуется {required_slots}, "
                    f"доступно {max_orders - used_orders}. "
                    "Обновите тариф для увеличения лимита."
                )
            )

    # Финальная проверка с блокировкой для атомарности
    stmt = (
        select(CompanyTariffState)
        .where(CompanyTariffState.company_id == company_id)
        .with_for_update()
    )

    result = await session.execute(stmt)
    state = result.scalar_one_or_none()

    if not state:
        raise CustomHTTPException(
            status_code=403,
            company_id=company_id,
            detail=(
                "У компании нет активного тарифа. "
                "Обратитесь к администратору для назначения тарифа."
            )
        )

    # Проверяем актуальные данные из БД
    max_orders = state.max_orders
    used_orders = state.used_orders or 0

    # Безлимит - пропускаем
    if max_orders is None:
        return

    # Лимит 0 - отказываем
    if max_orders == 0:
        raise CustomHTTPException(
            status_code=403,
            company_id=company_id,
            detail=(
                "Тарифный план не позволяет создавать заявки. "
                "Обновите тариф для доступа к функционалу."
            )
        )

    # Проверяем превышение лимита
    if used_orders + required_slots > max_orders:
        available = max_orders - used_orders
        raise CustomHTTPException(
            status_code=403,
            company_id=company_id,
            detail=(
                f"Превышен лимит заявок ({used_orders}/{max_orders}). "
                f"Требуется {required_slots}, доступно {available}. "
                "Обновите тариф для увеличения лимита."
            )
        )

    # Всё ок - пропускаем


async def increment_order_count(
    session: AsyncSession,
    company_id: int,
    delta: int = 1
) -> None:
    from apps.tariff_app.repositories.company_tariff_state_repository import (
        CompanyTariffStateRepository
    )

    repo = CompanyTariffStateRepository(session)
    await repo.increment_usage(company_id, orders=delta)

    # Инвалидируем кеш - он обновится при следующем запросе
    await tariff_cache.invalidate_cache(company_id)


async def decrement_order_count(
    session: AsyncSession,
    company_id: int,
    delta: int = 1
) -> None:
    # Блокируем state для обновления
    stmt = (
        select(CompanyTariffState)
        .where(CompanyTariffState.company_id == company_id)
        .with_for_update()
    )

    result = await session.execute(stmt)
    state = result.scalar_one_or_none()

    if not state:
        # Нет state - ничего не делаем (молча игнорируем)
        return

    # Уменьшаем счётчик, но не ниже 0
    new_value = max(0, (state.used_orders or 0) - delta)
    state.used_orders = new_value

    await session.flush()

    # Инвалидируем кеш - он обновится при следующем запросе
    await tariff_cache.invalidate_cache(company_id)
