from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions.api.tariff_control import (
    TariffNotFoundError, TariffForbiddenError
)

from apps.tariff_app.services import tariff_cache
from apps.tariff_app.repositories import CompanyTariffStateRepository


def check_employee_limit_zero(max_employees: int) -> None:
    """Проверяет, что лимит сотрудников не равен нулю."""
    if max_employees == 0:
        raise TariffForbiddenError(
            detail="Тариф компании запрещает создание сотрудников (лимит: 0)."
        )


def check_employee_limit_exceeded(
    used: int, max_value: int, required: int
) -> None:
    """Проверяет превышение лимита сотрудников."""
    if used + required > max_value:
        raise TariffForbiddenError(
            detail=(
                f"Достигнут лимит сотрудников по тарифу. "
                f"Использовано: {used}, Максимум: {max_value}, "
                f"Требуется: {required}."
            )
        )


async def check_employee_limit_available(
    session: AsyncSession,
    company_id: int,
    required_slots: int = 1
) -> None:
    """
    Проверить доступность мест для создания сотрудников.
    """
    repo = CompanyTariffStateRepository(session)

    cached = await tariff_cache.get_cached_limits(company_id)

    if cached and cached.get("has_tariff"):
        limits = cached["limits"]
        max_emp = limits.get("max_employees")
        used_emp = limits.get("used_employees", 0)

        if max_emp is not None:
            check_employee_limit_zero(max_emp)
            check_employee_limit_exceeded(used_emp, max_emp, required_slots)

    state = await repo.get_by_company(company_id, for_update=True)
    if not state:
        raise TariffNotFoundError

    max_emp = state.max_employees
    used_emp = state.used_employees or 0

    # Безлимит - пропускаем проверку
    if max_emp is None:
        return

    check_employee_limit_zero(max_emp)
    check_employee_limit_exceeded(used_emp, max_emp, required_slots)


async def increment_employee_count(
    session: AsyncSession,
    company_id: int,
    delta: int = 1
) -> None:
    """
    Увеличить счётчик использованных сотрудников.
    """
    repo = CompanyTariffStateRepository(session)
    await repo.increment_usage(company_id, employees=delta)
    await tariff_cache.invalidate_cache(company_id)


async def decrement_employee_count(
    session: AsyncSession,
    company_id: int,
    delta: int = 1
) -> None:
    """
    Уменьшить счётчик использованных сотрудников.
    """
    repo = CompanyTariffStateRepository(session)
    await repo.decrement_usage_safe(company_id, employees=delta)
    await tariff_cache.invalidate_cache(company_id)


async def recalculate_employee_count(
    session: AsyncSession,
    company_id: int
) -> int:
    """
    Пересчитать фактическое количество сотрудников в компании.
    """
    repo = CompanyTariffStateRepository(session)

    # Блокируем строку тарифа
    state = await repo.get_by_company(company_id, for_update=True)
    if not state:
        return 0

    # Получаем фактическое количество сотрудников через репозиторий
    actual_count = await repo.count_actual_employees(company_id)

    # Обновляем used_employees
    state.used_employees = actual_count
    await session.flush()

    # Инвалидируем кеш
    await tariff_cache.invalidate_cache(company_id)

    return actual_count
