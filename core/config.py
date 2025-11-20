from pathlib import Path
from typing import ClassVar, Final
from datetime import datetime as Datetime, timezone, timedelta
from pydantic_settings import BaseSettings, SettingsConfigDict


_ROOT = Path(__file__).parent.parent


def to_moscow(value: Datetime):
    if isinstance(value, Datetime):
        msk_tz = timezone(timedelta(hours=3))
        return value.astimezone(msk_tz)
    return value


def format_date(value, format: str = "%d.%m.%Y"):
    value = to_moscow(value)
    return value.strftime(format) if isinstance(value, Datetime) else value


def format_datetime(
        value, format: str = "%d.%m.%Y %H:%M:%S"):
    value = to_moscow(value)
    return value.strftime(format) if isinstance(value, Datetime) else value


class Settings(BaseSettings):
    BASE_DIR: Path = _ROOT
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / '.env',
        env_file_encoding='utf-8',
        extra='allow',
    )

    database_url: str

    # === Redis ===
    redis_url: str

    # === Секреты и креды ===
    secret_key: str
    salt: str

    # === base admin info ===
    admin_username: str
    admin_password: str

    # === Таймаут токена (секунды) ===
    jwt_token_expiration: Final[int] = 60 * 60 * 24 * 30  # 30 дней

    # === Кеширование тарифов (секунды) ===
    tariff_cache_ttl: Final[int] = 60 * 60 * 24 * 30  # 30 дней

    entries_per_page: Final[int] = 20

    document_max_size_mb: Final[int] = 10 * 1024 * 1024  # 10 MB

    # === Лимит фото в поверке ===
    image_limit_per_verification: Final[int] = 15
    image_max_size_mb: Final[int] = 5 * 1024 * 1024  # 5 MB

    # === URL ===
    logout_url: str = "/logout"
    login_url: str = "/"

    company_url: str = "/companies"
    verification_url: str = "/verification"
    calendar_url: str = "/calendar"

    max_int: int = 2147483647

    allowed_image_formats: set[str] = {
        'image/jpeg', 'image/jpg', 'image/png', 'image/gif',
        'image/webp', 'image/bmp', 'image/tiff', 'image/heic',
        'image/heif'
    }

    allowed_photo_ext: set[str] = {
        "jpeg", "jpg", "png", "heic", "heif", "webp"
    }

    url_path_map: ClassVar[dict[str, str]] = {
        "admin": company_url,
        "director": company_url,
        "auditor": verification_url,
        "dispatcher1": calendar_url,
        "dispatcher2": calendar_url,
        "verifier": verification_url,
    }


settings = Settings()
