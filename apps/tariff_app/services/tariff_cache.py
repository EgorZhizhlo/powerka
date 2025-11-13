import json
from typing import Optional, Dict, Any

from infrastructure.cache import redis
from core.config import settings
from core.utils.time_utils import date_utc_now


class TariffCacheService:
    """Управление кешем тарифных лимитов компаний"""

    @property
    def cache_ttl(self) -> int:
        """Получить TTL кеша из настроек"""
        return settings.tariff_cache_ttl

    @staticmethod
    def _get_cache_key(company_id: int) -> str:
        """Получить ключ кеша для компании"""
        return f"company:{company_id}:tariff_limits"

    @staticmethod
    def _serialize_tariff_data(state: Any) -> Dict[str, Any]:
        """
        Сериализовать данные тарифа для кеширования
        """
        if not state:
            return {
                'has_tariff': False,
                'cached_at': date_utc_now().isoformat()
            }

        data = {
            'has_tariff': True,
            'cached_at': date_utc_now().isoformat(),
            'title': state.title,
            'valid_from': (
                state.valid_from.isoformat() if state.valid_from else None
            ),
            'valid_to': (
                state.valid_to.isoformat() if state.valid_to else None
            ),
            'is_expired': (
                state.valid_to and state.valid_to < date_utc_now()
            ),
            'limits': {
                'max_employees': state.max_employees,
                'used_employees': state.used_employees,
                'max_verifications': state.max_verifications,
                'used_verifications': state.used_verifications,
                'max_orders': state.max_orders,
                'used_orders': state.used_orders,
            },
            'percentages': {
                'employees': round(
                    (state.used_employees / state.max_employees * 100)
                    if (state.max_employees and state.max_employees > 0)
                    else 0, 1
                ),
                'verifications': round(
                    (state.used_verifications / state.max_verifications * 100)
                    if (state.max_verifications and
                        state.max_verifications > 0)
                    else 0, 1
                ),
                'orders': round(
                    (state.used_orders / state.max_orders * 100)
                    if (state.max_orders and state.max_orders > 0)
                    else 0, 1
                ),
            },
            'automation': {
                'auto_manufacture_year': state.auto_manufacture_year,
                'auto_teams': state.auto_teams,
                'auto_metrolog': state.auto_metrolog,
            },
            'carry_over': {
                'verifications': state.carry_over_verifications,
                'orders': state.carry_over_orders,
            }
        }

        return data

    async def get_cached_limits(
        self, company_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Получить закешированную информацию о лимитах компании
        """
        key = self._get_cache_key(company_id)
        cached = await redis.get(key)

        if cached:
            try:
                return json.loads(cached)
            except json.JSONDecodeError:
                # Если кеш поврежден, удаляем его
                await redis.delete(key)
                return None

        return None

    async def set_cached_limits(
        self,
        company_id: int,
        state: Any
    ) -> None:
        """
        Закешировать информацию о лимитах компании
        """
        key = self._get_cache_key(company_id)
        data = self._serialize_tariff_data(state)

        await redis.setex(
            key,
            self.cache_ttl,
            json.dumps(data, ensure_ascii=False)
        )

    async def invalidate_cache(self, company_id: int) -> None:
        """
        Инвалидировать (удалить) кеш для компании
        """
        key = self._get_cache_key(company_id)
        await redis.delete(key)

    async def update_usage(
        self,
        company_id: int,
        field: str,
        delta: int
    ) -> None:
        """
        Обновить счётчик использования в кеше
        """
        key = self._get_cache_key(company_id)
        cached = await self.get_cached_limits(company_id)

        if not cached or not cached.get('has_tariff'):
            # Кеша нет или тариф не назначен - ничего не делаем
            return

        # Обновляем счётчик
        field_key = f'used_{field}'
        if field_key in cached['limits']:
            cached['limits'][field_key] += delta

            # Пересчитываем процент
            max_value = cached['limits'].get(f'max_{field}')
            used_value = cached['limits'][field_key]

            if max_value and max_value > 0:
                cached['percentages'][field] = round(
                    (used_value / max_value * 100), 1
                )

            # Сохраняем обновлённый кеш
            await redis.setex(
                key,
                self.cache_ttl,
                json.dumps(cached, ensure_ascii=False)
            )

    async def get_or_fetch_limits(
        self,
        company_id: int,
        fetch_callback
    ) -> Dict[str, Any]:
        """
        Получить лимиты из кеша или из БД с последующим кешированием
        """
        # Проверяем кеш
        cached = await self.get_cached_limits(company_id)
        if cached:
            return cached

        # Кеша нет - загружаем из БД
        state = await fetch_callback()

        # Кешируем данные
        await self.set_cached_limits(company_id, state)

        # Возвращаем сериализованные данные
        return self._serialize_tariff_data(state)


tariff_cache = TariffCacheService()
