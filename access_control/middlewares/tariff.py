from typing import Optional
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse, JSONResponse

from sqlalchemy import select, update

from models import CompanyTariffState, CompanyModel
from models.enums import EmployeeStatus

from access_control import bump_jwt_token_version

from core.utils.time_utils import date_utc_now

from infrastructure.db.session import async_session_maker


class TariffMiddleware(BaseHTTPMiddleware):
    """Проверка тарифа компании перед доступом к функционалу"""

    # Пути, где проверяется тариф (применяется middleware)
    PROTECTED_PATHS = [
        '/calendar/',
        '/verification/',
        '/companies/',
    ]

    # Безопасные методы (только чтение)
    SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS'}

    async def dispatch(self, request: Request, call_next):
        # Проверяем, нужно ли применять middleware к этому пути
        if not self._should_check_tariff(request.url.path):
            return await call_next(request)

        # Проверяем, что пользователь аутентифицирован
        auth_token = request.cookies.get("auth_token")
        company_token = request.cookies.get("company_info_token")

        if not auth_token or not company_token:
            # Не аутентифицирован - пропускаем (AuthMiddleware обработает)
            return await call_next(request)

        # Извлекаем данные из токенов (уже проверены в AuthMiddleware)
        from access_control.tokens import verify_token, verify_untimed_token

        try:
            user_data = verify_token(auth_token)
            comp_data = verify_untimed_token(company_token)
        except Exception:
            # Невалидные токены - пропускаем
            return await call_next(request)

        # Админы имеют полный доступ - пропускаем проверку тарифа
        if user_data.get('status') == EmployeeStatus.admin:
            return await call_next(request)

        # Извлекаем company_id из query параметров
        company_id = self._extract_company_id(request)
        if not company_id:
            # Нет company_id - не можем проверить тариф
            return await call_next(request)

        # Проверяем, что пользователь связан с этой компанией
        user_company_ids = comp_data.get('all_company_ids', [])
        if company_id not in user_company_ids:
            # Пользователь не связан с компанией - пропускаем
            return await call_next(request)

        # Проверяем тариф компании
        tariff_check = await self._check_company_tariff(
            company_id, request.method
        )

        if not tariff_check['allowed']:
            # Доступ запрещён - возвращаем ошибку
            return self._create_error_response(
                request, tariff_check['reason'], company_id
            )

        # Всё ок - пропускаем запрос
        return await call_next(request)

    def _should_check_tariff(self, path: str) -> bool:
        """
        Проверить, нужно ли применять middleware к данному пути

        Игнорируются:
        - Все пути НЕ начинающиеся с /calendar/, /verification/, /companies/
        - Точные пути /companies и /companies/ (без подпутей)
        """
        # Специальная проверка для /companies - исключаем только базовые пути
        if path == '/companies' or path == '/companies/':
            return False

        # Проверяем, начинается ли путь с одного из защищённых
        for protected in self.PROTECTED_PATHS:
            if path.startswith(protected):
                return True

        return False

    def _extract_company_id(self, request: Request) -> Optional[int]:
        """Извлечь company_id из query параметров"""
        company_id_str = request.query_params.get('company_id')
        if company_id_str:
            try:
                return int(company_id_str)
            except (ValueError, TypeError):
                return None
        return None

    async def _check_company_tariff(
        self, company_id: int, method: str
    ) -> dict:
        """
        Проверить тариф компании
        """
        # Lazy import для избежания циклических зависимостей
        from apps.tariff_app.services.tariff_cache import (
            tariff_cache
        )

        # Пытаемся получить state из кеша
        cached_state = await tariff_cache.get_cached_limits(company_id)

        if cached_state:
            # Нашли в кеше - используем
            has_tariff = cached_state.get('has_tariff', False)
            valid_to_str = cached_state.get('valid_to')

            if not has_tariff:
                # Нет тарифа - отказываем и обновляем is_active
                await self._update_company_active_status(company_id, False)
                return {
                    'allowed': False,
                    'reason': 'У компании нет активного тарифа'
                }

            # Парсим дату
            if valid_to_str:
                from datetime import datetime
                valid_to = datetime.fromisoformat(valid_to_str).date()
            else:
                # Бессрочный тариф
                valid_to = None
        else:
            # Нет в кеше - обращаемся к БД
            state = await self._fetch_state_from_db(company_id)

            if not state:
                # Нет тарифа - отказываем и обновляем is_active
                await self._update_company_active_status(company_id, False)
                return {
                    'allowed': False,
                    'reason': 'У компании нет активного тарифа'
                }

            # Кешируем найденный state
            async with async_session_maker() as session:
                from apps.tariff_app.repositories.\
                    company_tariff_history import (
                        CompanyTariffHistoryRepository
                    )
                history_repo = CompanyTariffHistoryRepository(session)
                active_history = await history_repo.get_active_by_company(
                    company_id
                )
                await tariff_cache.set_cached_limits(
                    company_id, state, active_history
                )

            valid_to = state.valid_to

        # Если тариф бессрочный - пропускаем
        if not valid_to:
            return {'allowed': True, 'reason': ''}

        # Проверяем срок действия
        today = date_utc_now()
        days_overdue = (today - valid_to).days

        # Просрочка больше 180 дней - полный отказ
        if days_overdue > 180:
            return {
                'allowed': False,
                'reason': (
                    f'Тариф просрочен более чем на 180 дней '
                    f'(истёк {valid_to.strftime("%d.%m.%Y")}). '
                    f'Обратитесь к администратору для продления.'
                )
            }

        # Просрочка от 1 до 180 дней - только чтение
        if 0 < days_overdue <= 180:
            if method not in self.SAFE_METHODS:
                return {
                    'allowed': False,
                    'reason': (
                        f'Тариф просрочен на {days_overdue} дней '
                        f'(истёк {valid_to.strftime("%d.%m.%Y")}). '
                        f'Операции записи запрещены. '
                        f'Обратитесь к администратору для продления.'
                    )
                }

        # Тариф в порядке
        return {'allowed': True, 'reason': ''}

    async def _fetch_state_from_db(
        self, company_id: int
    ) -> Optional[CompanyTariffState]:
        """Получить state из БД"""
        async with async_session_maker() as session:
            stmt = select(CompanyTariffState).where(
                CompanyTariffState.company_id == company_id
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def _update_company_active_status(
        self, company_id: int, is_active: bool
    ) -> None:
        """
        Обновить статус активности компании и инвалидировать
        кеш сотрудников
        """
        async with async_session_maker() as session:
            # Обновляем is_active
            stmt = (
                update(CompanyModel)
                .where(CompanyModel.id == company_id)
                .values(is_active=is_active)
            )
            await session.execute(stmt)

            # Получаем список сотрудников для инвалидации кеша
            stmt = (
                select(CompanyModel)
                .where(CompanyModel.id == company_id)
            )
            result = await session.execute(stmt)
            company = result.scalar_one_or_none()

            if company:
                # Получаем ID сотрудников через связь many-to-many
                from models import EmployeeModel
                stmt = (
                    select(EmployeeModel.id)
                    .where(
                        EmployeeModel.companies.any(
                            CompanyModel.id == company_id
                        )
                    )
                )
                result = await session.execute(stmt)
                employee_ids = result.scalars().all()

                # Обновляем версию токенов для всех сотрудников
                # (включая админов - они тоже должны обновиться)
                for emp_id in employee_ids:
                    await bump_jwt_token_version(
                        f"user:{emp_id}:company_version"
                    )

            await session.commit()

    def _create_error_response(
        self, request: Request, reason: str, company_id: int
    ):
        """Создать ответ с ошибкой"""
        # Если это API запрос - возвращаем JSON
        if request.url.path.startswith('/api/'):
            return JSONResponse(
                status_code=403,
                content={
                    'detail': reason,
                    'code': 'TARIFF_ACCESS_DENIED',
                    'company_id': company_id
                }
            )

        # Иначе - редирект на страницу просмотра тарифа с ошибкой
        return RedirectResponse(
            url=f'/tariff/view/?company_id={company_id}&error=access_denied',
            status_code=303
        )
