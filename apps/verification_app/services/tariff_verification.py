from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions.api.tariff_control import (
    TariffForbiddenError, TariffNotFoundError
)

from apps.tariff_app.services.tariff_cache import tariff_cache
from apps.tariff_app.repositories.company_tariff_state import (
    CompanyTariffStateRepository
)


def check_verification_limit_zero(max_verif: int) -> None:
    """Проверяет, что лимит поверок не равен нулю."""
    if max_verif == 0:
        raise TariffForbiddenError(
            detail=(
                "Тарифный план не позволяет создавать записи поверок. "
                "Обновите тариф для доступа к функционалу."
            )
        )


def check_verification_limit_exceeded(
    used_verif: int, max_verif: int, required_slots: int
) -> None:
    """Проверяет превышение лимита поверок."""
    if used_verif + required_slots > max_verif:
        available = max_verif - used_verif
        raise TariffForbiddenError(
            detail=(
                f"Превышен лимит записей поверок ({used_verif}/{max_verif}). "
                f"Требуется {required_slots}, доступно {available}. "
                "Обновите тариф для увеличения лимита."
            )
        )


async def check_verification_limit_available(
    session: AsyncSession,
    company_id: int,
    required_slots: int = 1
) -> None:
    """Проверяет наличие доступного лимита поверок."""
    repo = CompanyTariffStateRepository(session)

    # Быстрая проверка по кешу
    cached = await tariff_cache.get_cached_limits(company_id)

    if cached and cached.get("has_tariff"):
        limits = cached.get("limits", {})
        max_verif = limits.get("max_verifications")
        used_verif = limits.get("used_verifications", 0)

        if max_verif is not None:
            check_verification_limit_zero(max_verif)
            check_verification_limit_exceeded(
                used_verif, max_verif, required_slots
            )

    # Проверка с блокировкой для защиты от гонок
    state = await repo.get_by_company(company_id, for_update=True)
    if not state:
        raise TariffNotFoundError

    max_verif = state.max_verifications
    used_verif = state.used_verifications or 0

    # Безлимит - пропускаем
    if max_verif is None:
        return

    check_verification_limit_zero(max_verif)
    check_verification_limit_exceeded(
        used_verif, max_verif, required_slots
    )


async def increment_verification_count(
    session: AsyncSession,
    company_id: int,
    delta: int = 1
) -> None:
    """Увеличивает счётчик поверок."""
    repo = CompanyTariffStateRepository(session)
    await repo.increment_usage(company_id, verifications=delta)
    await tariff_cache.invalidate_cache(company_id)


async def decrement_verification_count(
    session: AsyncSession,
    company_id: int,
    delta: int = 1
) -> None:
    """Уменьшает счётчик поверок (без ухода в минус)."""
    repo = CompanyTariffStateRepository(session)
    await repo.decrement_usage_safe(company_id, verifications=delta)
    await tariff_cache.invalidate_cache(company_id)
