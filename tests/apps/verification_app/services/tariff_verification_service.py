import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.exceptions import CustomHTTPException

from apps.verification_app.services.tariff_verification import (
    check_verification_limit_zero,
    check_verification_limit_exceeded,
    check_verification_limit_available,
    increment_verification_count,
    decrement_verification_count,
)

SERVICE_PATH = "apps.verification_app.services.tariff_verification_service"


def test_check_verification_limit_zero_ok():
    check_verification_limit_zero(company_id=1, max_verif=10)  # no exception


def test_check_verification_limit_zero_fail():
    with pytest.raises(CustomHTTPException) as exc:
        check_verification_limit_zero(company_id=5, max_verif=0)

    assert exc.value.status_code == 403
    assert exc.value.company_id == 5
    assert "Превышен лимит" in exc.value.detail


def test_check_verification_limit_exceeded_ok():
    check_verification_limit_exceeded(
        company_id=1, used_verif=5, max_verif=10, required_slots=3
    )  # no exception


def test_check_verification_limit_exceeded_fail():
    with pytest.raises(CustomHTTPException) as exc:
        check_verification_limit_exceeded(
            company_id=1, used_verif=9, max_verif=10, required_slots=3
        )

    assert "Требуется 3, доступно 1" in exc.value.detail


@pytest.mark.asyncio
async def test_limit_available_cached_unlimited():
    """
    Если в кэше max_verif=None — функция должна завершиться без проверки БД
    """
    fake_session = AsyncMock()

    mock_cache = AsyncMock()
    mock_cache.get_cached_limits.return_value = {
        "has_tariff": True,
        "limits": {
            "max_verifications": None,  # ← безлимит
            "used_verifications": 0,
        }
    }

    with patch(SERVICE_PATH + ".tariff_cache", mock_cache):
        await check_verification_limit_available(fake_session, company_id=1)

    fake_session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_limit_available_cached_exceeded():
    """
    Если в кэше уже видно превышение — ошибка должна подняться без БД
    """
    fake_session = AsyncMock()

    mock_cache = AsyncMock()
    mock_cache.get_cached_limits.return_value = {
        "has_tariff": True,
        "limits": {
            "max_verifications": 10,
            "used_verifications": 9,
        }
    }

    with patch(SERVICE_PATH + ".tariff_cache", mock_cache):
        with pytest.raises(CustomHTTPException):
            await check_verification_limit_available(
                fake_session, company_id=1, required_slots=2
            )


@pytest.mark.asyncio
async def test_limit_available_no_state_in_db():
    """
    Если в БД нет CompanyTariffState — ошибка.
    """
    fake_session = AsyncMock()
    execute_mock = fake_session.execute.return_value
    execute_mock.scalar_one_or_none.return_value = None

    mock_cache = AsyncMock()
    mock_cache.get_cached_limits.return_value = None  # кэша нет

    with patch(SERVICE_PATH + ".tariff_cache", mock_cache):
        with pytest.raises(CustomHTTPException):
            await check_verification_limit_available(
                fake_session, company_id=1
            )


@pytest.mark.asyncio
async def test_limit_available_db_unlimited():
    """
    Проверка безлимита из БД.
    """
    fake_state = MagicMock()
    fake_state.company_id = 1
    fake_state.max_verifications = None
    fake_state.used_verifications = 7

    fake_session = AsyncMock()
    execute_mock = fake_session.execute.return_value
    execute_mock.scalar_one_or_none.return_value = fake_state

    mock_cache = AsyncMock()
    mock_cache.get_cached_limits.return_value = None

    with patch(SERVICE_PATH + ".tariff_cache", mock_cache):
        await check_verification_limit_available(fake_session, 1)


@pytest.mark.asyncio
async def test_limit_available_db_exceeded():
    fake_state = MagicMock()
    fake_state.company_id = 1
    fake_state.max_verifications = 10
    fake_state.used_verifications = 9

    fake_session = AsyncMock()
    execute_mock = fake_session.execute.return_value
    execute_mock.scalar_one_or_none.return_value = fake_state

    mock_cache = AsyncMock()
    mock_cache.get_cached_limits.return_value = None

    with patch(SERVICE_PATH + ".tariff_cache", mock_cache):
        with pytest.raises(CustomHTTPException):
            await check_verification_limit_available(
                fake_session, company_id=1, required_slots=2
            )


@pytest.mark.asyncio
async def test_increment_verification_count():
    fake_session = AsyncMock()

    mock_repo = AsyncMock()
    mock_repo.increment_usage = AsyncMock()

    mock_repo_class = MagicMock(return_value=mock_repo)

    mock_cache = AsyncMock()

    with patch(
        SERVICE_PATH + ".CompanyTariffStateRepository",
        mock_repo_class
    ):
        with patch(SERVICE_PATH + ".tariff_cache", mock_cache):
            await increment_verification_count(fake_session, 5, delta=3)

    mock_repo.increment_usage.assert_awaited_with(5, verifications=3)
    mock_cache.invalidate_cache.assert_awaited_with(5)


@pytest.mark.asyncio
async def test_decrement_verification_count_ok():
    fake_state = MagicMock()
    fake_state.company_id = 1
    fake_state.used_verifications = 5

    fake_session = AsyncMock()
    fake_session.flush = AsyncMock()
    execute_mock = fake_session.execute.return_value
    execute_mock.scalar_one_or_none.return_value = fake_state

    mock_cache = AsyncMock()

    with patch(SERVICE_PATH + ".tariff_cache", mock_cache):
        await decrement_verification_count(fake_session, 1, delta=3)

    assert fake_state.used_verifications == 2
    fake_session.flush.assert_awaited()
    mock_cache.invalidate_cache.assert_awaited_with(1)


@pytest.mark.asyncio
async def test_decrement_verification_count_no_state():
    """
    Если state не найден — просто без ошибок
    """
    fake_session = AsyncMock()
    fake_session.flush = AsyncMock()
    execute_mock = fake_session.execute.return_value
    execute_mock.scalar_one_or_none.return_value = None

    mock_cache = AsyncMock()

    with patch(SERVICE_PATH + ".tariff_cache", mock_cache):
        await decrement_verification_count(fake_session, 1, delta=5)

    # flush не должен вызываться
    fake_session.flush.assert_not_called()
