from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from core.exceptions.api import BadRequestError


def datetime_utc_now():
    return datetime.now(tz=timezone.utc)


def date_utc_now():
    return datetime_utc_now().date()


def validate_company_timezone(
    schema_tz: str,
    cached_tz: str,
    company_id: int
) -> None:
    """
    Проверяет соответствие timezone из схемы данных и из кеша/БД.
    """
    if schema_tz != cached_tz:
        raise BadRequestError(
            detail=(
                f"Несоответствие timezone: отправлено '{schema_tz}', "
                f"ожидается '{cached_tz}' для компании {company_id}. "
                "Пожалуйста, обновите страницу."
            )
        )


def format_timestamp_with_tz(
    dt: Optional[datetime],
    tz_name: str,
    fmt: str = "%d.%m.%Y %H:%M"
) -> Optional[str]:
    """
    Форматирует timestamp с учетом timezone.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    local_dt = dt.astimezone(ZoneInfo(tz_name))
    return local_dt.strftime(fmt)
