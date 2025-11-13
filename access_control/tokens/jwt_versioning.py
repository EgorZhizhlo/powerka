from core.config import settings
from infrastructure.cache import redis


jwt_token_exp = settings.jwt_token_expiration


async def bump_jwt_token_version(key: str) -> int:
    """
    Увеличить версию токена (на login/logout).
    Возвращает новую версию.
    """
    version = await redis.incr(key)
    await redis.expire(key, jwt_token_exp)
    return version


async def get_jwt_token_version(key: str) -> int:
    """
    Возвращает текущую версию (0, если нет ключа).
    """
    v = await redis.get(key)
    return int(v) if v else 0


async def reset_jwt_token_version(key: str):
    """
    Сброс версий (например, при logout).
    """
    await redis.delete(key)
