from infrastructure.cache import redis


async def clear_verification_cache(company_id: int):
    cursor = b"0"
    pattern = f"verification_entries:{company_id}:*"
    while cursor:
        cursor, keys = await redis.scan(
            cursor=cursor, match=pattern, count=100
        )
        if keys:
            await redis.delete(*keys)
