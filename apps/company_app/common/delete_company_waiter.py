from infrastructure.cache.redis_client import redis


def _company_delete_key(company_id: int) -> str:
    return f"company:delete:{company_id}"


def _company_delete_lock_key(company_id: int) -> str:
    return f"company:delete:lock:{company_id}"


async def _register_delete_vote(company_id: int, admin_user_id: int) -> int:
    key = _company_delete_key(company_id)
    await redis.sadd(key, str(admin_user_id))
    ttl = await redis.ttl(key)
    if ttl is None or ttl < 0:
        await redis.expire(key, 300)
    return await redis.scard(key)


async def _clear_delete_votes(company_id: int) -> None:
    await redis.delete(_company_delete_key(company_id))


async def _try_acquire_delete_lock(company_id: int, ttl: int = 30) -> bool:
    return await redis.set(
        _company_delete_lock_key(company_id), "1", ex=ttl, nx=True
    ) is True


async def _release_delete_lock(company_id: int) -> None:
    await redis.delete(_company_delete_lock_key(company_id))
