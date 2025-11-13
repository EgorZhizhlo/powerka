from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.cache import redis
from models import CompanyModel


class CompanyTimezoneCacheService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @staticmethod
    def _cache_key(company_id: int) -> str:
        """Генерирует ключ для кеша timezone компании"""
        return f"company:{company_id}:timezone"

    async def get_timezone(
        self,
        company_id: int,
        session: Optional[AsyncSession] = None
    ) -> str:
        """Получает timezone компании из кеша или БД."""
        # Проверяем кеш
        cache_key = self._cache_key(company_id)
        cached_tz = await redis.get(cache_key)

        if cached_tz:
            return cached_tz

        # Если нет в кеше - идем в БД
        if session is None:
            # Если сессия не передана - создаем временную
            from infrastructure.db.session import async_session_maker
            async with async_session_maker() as temp_session:
                timezone = await self._fetch_from_db(
                    company_id, temp_session
                )
        else:
            timezone = await self._fetch_from_db(company_id, session)

        # Кешируем результат (если найден)
        if timezone:
            await self.set_timezone(company_id, timezone)

        return timezone or "Europe/Moscow"

    async def _fetch_from_db(
        self,
        company_id: int,
        session: AsyncSession
    ) -> Optional[str]:
        """Получает timezone из БД."""
        result = await session.execute(
            select(CompanyModel.timezone)
            .where(CompanyModel.id == company_id)
        )
        return result.scalar_one_or_none()

    async def set_timezone(self, company_id: int, timezone: str) -> None:
        """Устанавливает timezone в кеш."""
        cache_key = self._cache_key(company_id)
        await redis.set(cache_key, timezone)

    async def invalidate_timezone(self, company_id: int) -> None:
        """Удаляет timezone из кеша."""
        cache_key = self._cache_key(company_id)
        await redis.delete(cache_key)

    async def refresh_timezone(
        self,
        company_id: int,
        session: AsyncSession
    ) -> str:
        """Принудительно обновляет timezone в кеше из БД."""
        timezone = await self._fetch_from_db(company_id, session)
        if timezone:
            await self.set_timezone(company_id, timezone)
            return timezone

        # Если компания удалена - очищаем кеш
        await self.invalidate_timezone(company_id)
        return "Europe/Moscow"


company_tz_cache = CompanyTimezoneCacheService()
