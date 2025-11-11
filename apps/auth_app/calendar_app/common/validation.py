from datetime import date as date_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models import RouteEmployeeAssignmentModel


async def _assigned(
        route_id: int, d: date_, session: AsyncSession) -> bool:
    return bool(
        await session.scalar(
            select(RouteEmployeeAssignmentModel.employee_id)
            .where(
                RouteEmployeeAssignmentModel.route_id == route_id,
                RouteEmployeeAssignmentModel.date == d
            )
        )
    )
