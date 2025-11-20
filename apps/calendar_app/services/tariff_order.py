from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions.api.tariff_control import (
    TariffForbiddenError, TariffNotFoundError
)

from apps.tariff_app.services.tariff_cache import tariff_cache
from apps.tariff_app.repositories.company_tariff_state import (
    CompanyTariffStateRepository
)


def check_order_limit_zero(max_orders: int) -> None:
    """Проверяет, что лимит не равен нулю."""
    if max_orders == 0:
        raise TariffForbiddenError(
            detail=(
                "Тарифный план не позволяет создавать календарные заявки. "
                "Обновите тариф для доступа к функционалу."
            )
        )


def check_order_limit_exceeded(
    used_orders: int, max_orders: int, required_slots: int
) -> None:
    """Проверяет превышение доступного лимита заявок."""
    if used_orders + required_slots > max_orders:
        available = max_orders - used_orders
        raise TariffForbiddenError(
            detail=(
                f"Превышен лимит календарных заявок ({used_orders}/{max_orders}). "
                f"Требуется {required_slots}, доступно {available}. "
                "Обновите тариф для увеличения лимита."
            )
        )


async def check_order_limit_available(
    session: AsyncSession,
    company_id: int,
    required_slots: int = 1
) -> None:
    """Проверяет наличие свободного лимита календарных заявок."""
    repo = CompanyTariffStateRepository(session)

    # Быстрая проверка по кешу
    cached_limits = await tariff_cache.get_cached_limits(company_id)

    if cached_limits and cached_limits.get('has_tariff'):
        limits = cached_limits.get('limits', {})
        max_orders = limits.get('max_orders')
        used_orders = limits.get('used_orders', 0)

        # Если безлимит (None) - сразу пропускаем
        if max_orders is not None:
            check_order_limit_zero(max_orders)
            check_order_limit_exceeded(
                used_orders, max_orders, required_slots
            )

    # Проверка с блокировкой для защиты от гонок
    state = await repo.get_by_company(company_id, for_update=True)
    if not state:
        raise TariffNotFoundError

    max_orders = state.max_orders
    used_orders = state.used_orders or 0

    # Безлимит - пропускаем
    if max_orders is None:
        return

    check_order_limit_zero(max_orders)
    check_order_limit_exceeded(
        used_orders, max_orders, required_slots
    )


async def increment_order_count(
    session: AsyncSession,
    company_id: int,
    delta: int = 1
) -> None:
    """Увеличивает счётчик использованных заявок."""
    repo = CompanyTariffStateRepository(session)
    await repo.increment_usage(company_id, orders=delta)
    await tariff_cache.invalidate_cache(company_id)


async def decrement_order_count(
    session: AsyncSession,
    company_id: int,
    delta: int = 1
) -> None:
    """Уменьшает счётчик использованных заявок (с защитой от гонок)."""
    repo = CompanyTariffStateRepository(session)
    await repo.decrement_usage_safe(company_id, orders=delta)
    await tariff_cache.invalidate_cache(company_id)
