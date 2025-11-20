import base64
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import CompanyModel

from core.exceptions.app.common import NotFoundError

from apps.company_app.repositories import CompanyRepository


async def make_context(
    session: AsyncSession,
    user_data: dict,
    company_id: int,
):
    repo = CompanyRepository(session=session, company_id=company_id)

    row = await repo.get_company_for_context()
    # Выполняем запрос
    result = await session.execute(
        select(
            CompanyModel.id,
            CompanyModel.name,
            CompanyModel.image,
            CompanyModel.auto_teams,
            CompanyModel.is_active
        ).where(CompanyModel.id == company_id)
    )
    row = result.mappings().first()

    # Если такой компании нет — бросаем 404
    if row is None:
        raise NotFoundError(
            company_id=company_id,
            detail="Компания не найдена!"
        )

    # Преобразуем RowMapping в словарь
    company: dict = dict(row)

    company_image = company.get("image")
    if company_image:
        company["image"] = base64.b64encode(company_image).decode('utf-8')

    context = {
        **user_data.__dict__,
        **{"company_" + key: value for key, value in company.items()}
    }
    return context
