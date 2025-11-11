from collections import Counter
from typing import Iterable, List
from datetime import date as date_
from sqlalchemy.ext.asyncio import AsyncSession

from core.utils.time_utils import date_utc_now
from core.exceptions import HTTPException
from models import (
    VerificationEntryModel, VerificationLogModel, VerifierModel,
    ActNumberModel, TeamModel
)
from models.enums import EquipmentInfoType


async def act_number_for_create(
    company_id: int,
    entry_data,
    session: AsyncSession,
) -> ActNumberModel:
    """
    Получить или создать ActNumber для новой записи поверки.
    Использует репозиторий для оптимизированного запроса.
    """
    from apps.verification_app.repositories import ActNumberRepository

    do_not_touch: set[str] = {"company_id", "act_number", "series_id"}

    update_fields = entry_data.model_dump(
        exclude_unset=True,
        exclude=do_not_touch
    )

    repo = ActNumberRepository(session, company_id)
    return await repo.get_or_create_with_verifications(
        act_number=entry_data.act_number,
        series_id=entry_data.series_id,
        update_fields=update_fields,
    )


def check_act_number_limit(
    act_number_entry: ActNumberModel,
) -> None:
    if not act_number_entry:
        raise HTTPException(
            status_code=404,
            detail="Запись номера акта не была найдена."
        )

    if act_number_entry.count <= 0:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Лимит записей по номеру акта: "
                f"{act_number_entry.act_number} превышен."
            )
        )


def check_verifier_equipment(
        verifier,
) -> bool:
    if not verifier:
        return False

    if not verifier.equipments:
        return False

    for equipment in verifier.equipments:
        if equipment.equipment_info:
            info = [
                e_info
                for e_info in equipment.equipment_info
                if (
                    e_info.type == EquipmentInfoType.verification
                    and e_info.verif_limit_date is not None
                )
            ]
            if not info:
                return True

            latest_equipment_info = max(
                info, key=lambda x: x.verif_limit_date
            )
            if latest_equipment_info.verif_limit_date < date_utc_now():
                return False

    return True


async def get_verification_logs_of_verifier(
    verification_dates: Iterable,
    verification_limit: int,
    verifier_id: int,
    session: AsyncSession,
) -> List[VerificationLogModel]:
    """
    Получить или создать логи поверок для поверителя на указанные даты.
    Использует репозиторий для оптимизированного запроса.
    """
    from apps.verification_app.repositories import VerificationLogRepository

    dates_list = list(verification_dates)
    if not dates_list:
        return []

    repo = VerificationLogRepository(session)
    return await repo.get_logs_for_verifier(
        verifier_id=verifier_id,
        dates=dates_list,
        verification_limit=verification_limit,
    )


async def true_false_access_to_create_entry_with_this_verifier(
    verification_logs: List[VerificationLogModel],
    verification_entries_statistics: Counter,
) -> bool:
    for verification_log in verification_logs:
        statistic_sum = verification_entries_statistics.get(
            verification_log.verification_date, 0
        )
        if verification_log.verification_limit - statistic_sum < -3:
            return False
    return True


async def add_verification_limit(
    verification_logs: List[VerificationLogModel],
    verification_entries_statistics: Counter,
) -> None:
    for verification_log in verification_logs:
        statistic_sum = verification_entries_statistics.get(
            verification_log.verification_date, 0
        )
        verification_log.verification_limit += statistic_sum


async def sub_verification_limit(
    verification_logs: List[VerificationLogModel],
    verification_entries_statistics: Counter,
) -> None:
    for verification_log in verification_logs:
        statistic_sum = verification_entries_statistics.get(
            verification_log.verification_date, 0
        )
        verification_log.verification_limit -= statistic_sum


async def change_verifier_in_verification_entries(
    verifier_id: int,
    verification_entries: List[VerificationEntryModel],
    session: AsyncSession,
    company_id: int,
) -> None:
    """
    Изменить поверителя во всех записях поверки.
    Использует репозиторий для получения оборудования поверителя.
    """
    from apps.verification_app.repositories import VerifierRepository

    repo = VerifierRepository(session, company_id)
    valid_equipments = await repo.get_verifier_equipments(verifier_id)

    for ve in verification_entries:
        ve.verifier_id = verifier_id
        ve.equipments.clear()
        ve.equipments.extend(valid_equipments)


async def get_verifiers_in_employee_verifier_team_without_him(
        employee_verifier_id: int,
        team_id: int,
        session: AsyncSession,
        company_id: int,
) -> List[VerifierModel]:
    """
    Получить поверителей из команды employee_verifier, исключая его самого.
    Использует репозиторий для оптимизированного запроса.
    """
    from apps.verification_app.repositories import VerifierRepository

    repo = VerifierRepository(session, company_id)
    return await repo.get_verifiers_by_team(
        team_id=team_id,
        exclude_verifier_id=employee_verifier_id
    )


async def get_verifiers_without_team(
    employee_verifier_id: int,
    company_id: int,
    session: AsyncSession,
) -> List[VerifierModel]:
    """
    Получить поверителей без команды, исключая указанного.
    Использует репозиторий для оптимизированного запроса.
    """
    from apps.verification_app.repositories import VerifierRepository

    repo = VerifierRepository(session, company_id)
    return await repo.get_verifiers_without_team(
        exclude_verifier_id=employee_verifier_id
    )


async def get_teams_with_verifiers_without_employee_verifier_team(
    team_id: int,
    company_id: int,
    session: AsyncSession,
) -> List[TeamModel]:
    """
    Получить команды с поверителями, исключая указанную команду.
    Использует репозиторий для оптимизированного запроса.
    """
    from apps.verification_app.repositories import VerifierRepository

    repo = VerifierRepository(session, company_id)
    return await repo.get_teams_with_verifiers(
        exclude_team_id=team_id
    )


async def get_verifier_id_create(
    verification_date: date_,
    employee_verifier: VerifierModel,
    act_number_entry: ActNumberModel,
    verification_limit: int,
    company_id: int,
    session: AsyncSession
) -> int:
    verification_entries = act_number_entry.verification

    last_verifier_ids = set(
        e.verifier_id
        for e in verification_entries
    )

    verification_entries_statistics = Counter(
        entry.verification_date
        for entry in verification_entries
    )

    verification_entries_statistics_with_new = (
        verification_entries_statistics.copy()
    )
    verification_entries_statistics_with_new[verification_date] += 1

    employee_verifier_id = employee_verifier.id
    team_id = employee_verifier.team_id

    # Проверка поверителя по умолчанию
    if check_verifier_equipment(employee_verifier):
        verification_logs_of_employee_verifier = await get_verification_logs_of_verifier(
            verification_dates=verification_entries_statistics_with_new.keys(),
            verification_limit=verification_limit,
            verifier_id=employee_verifier_id,
            session=session
        )

        access_flag_to_create_entry = await true_false_access_to_create_entry_with_this_verifier(
            verification_logs=verification_logs_of_employee_verifier,
            verification_entries_statistics=verification_entries_statistics_with_new
        )

        if access_flag_to_create_entry:
            if last_verifier_ids == {employee_verifier_id}:
                await sub_verification_limit(
                    verification_logs=verification_logs_of_employee_verifier,
                    verification_entries_statistics=Counter(
                        {verification_date: 1})
                )
                await session.flush()
                return employee_verifier_id
            else:
                for last_verifier_id in last_verifier_ids:
                    verification_logs_of_last_verifier = await get_verification_logs_of_verifier(
                        verification_dates=verification_entries_statistics.keys(),
                        verification_limit=verification_limit,
                        verifier_id=last_verifier_id,
                        session=session
                    )
                    await add_verification_limit(
                        verification_logs=verification_logs_of_last_verifier,
                        verification_entries_statistics=verification_entries_statistics
                    )

                await sub_verification_limit(
                    verification_logs=verification_logs_of_employee_verifier,
                    verification_entries_statistics=verification_entries_statistics_with_new
                )
                await change_verifier_in_verification_entries(
                    verifier_id=employee_verifier_id,
                    verification_entries=act_number_entry.verification,
                    session=session,
                    company_id=company_id
                )
                await session.flush()
                return employee_verifier_id

    # Проверка поверителей в команде (кроме employee_verifier)
    if team_id:
        verifiers_in_employee_verifier_team = (
            await get_verifiers_in_employee_verifier_team_without_him(
                employee_verifier_id=employee_verifier_id,
                team_id=team_id,
                session=session,
                company_id=company_id
            )
        )

        for verifier_in_employee_verifier_team in verifiers_in_employee_verifier_team:
            if not check_verifier_equipment(verifier_in_employee_verifier_team):
                continue

            verifier_id_in_employee_verifier_team: int = verifier_in_employee_verifier_team.id

            verification_logs_of_verifier_in_employee_verifier_team = await get_verification_logs_of_verifier(
                verification_dates=verification_entries_statistics_with_new.keys(),
                verification_limit=verification_limit,
                verifier_id=verifier_id_in_employee_verifier_team,
                session=session
            )

            access_flag_to_create_entry = await true_false_access_to_create_entry_with_this_verifier(
                verification_logs=verification_logs_of_verifier_in_employee_verifier_team,
                verification_entries_statistics=verification_entries_statistics_with_new
            )

            if access_flag_to_create_entry:
                if last_verifier_ids == {verifier_id_in_employee_verifier_team}:
                    await sub_verification_limit(
                        verification_logs=verification_logs_of_verifier_in_employee_verifier_team,
                        verification_entries_statistics=Counter(
                            {verification_date: 1})
                    )
                    await session.flush()
                    return verifier_id_in_employee_verifier_team
                else:
                    for last_verifier_id in last_verifier_ids:
                        verification_logs_of_last_verifier = await get_verification_logs_of_verifier(
                            verification_dates=verification_entries_statistics.keys(),
                            verification_limit=verification_limit,
                            verifier_id=last_verifier_id,
                            session=session
                        )
                        await add_verification_limit(
                            verification_logs=verification_logs_of_last_verifier,
                            verification_entries_statistics=verification_entries_statistics
                        )
                    await sub_verification_limit(
                        verification_logs=verification_logs_of_verifier_in_employee_verifier_team,
                        verification_entries_statistics=verification_entries_statistics_with_new
                    )
                    await change_verifier_in_verification_entries(
                        verifier_id=verifier_id_in_employee_verifier_team,
                        verification_entries=act_number_entry.verification,
                        session=session,
                        company_id=company_id
                    )
                    await session.flush()
                    return verifier_id_in_employee_verifier_team

    # Проверка поверителей без команды и без поверителя по умолчанию
    verifiers_without_team = await get_verifiers_without_team(
        employee_verifier_id=employee_verifier_id,
        company_id=company_id,
        session=session
    )
    for verifier_without_team in verifiers_without_team:
        if not check_verifier_equipment(verifier_without_team):
            continue

        verifier_id_without_team: int = verifier_without_team.id

        verification_logs_of_verifier_without_team = await get_verification_logs_of_verifier(
            verification_dates=verification_entries_statistics_with_new.keys(),
            verification_limit=verification_limit,
            verifier_id=verifier_id_without_team,
            session=session
        )

        access_flag_to_create_entry = await true_false_access_to_create_entry_with_this_verifier(
            verification_logs=verification_logs_of_verifier_without_team,
            verification_entries_statistics=verification_entries_statistics_with_new
        )

        if access_flag_to_create_entry:
            if last_verifier_ids == {verifier_id_without_team}:
                await sub_verification_limit(
                    verification_logs=verification_logs_of_verifier_without_team,
                    verification_entries_statistics=Counter(
                        {verification_date: 1})
                )
                await session.flush()
                return verifier_id_without_team
            else:
                for last_verifier_id in last_verifier_ids:
                    verification_logs_of_last_verifier = await get_verification_logs_of_verifier(
                        verification_dates=verification_entries_statistics.keys(),
                        verification_limit=verification_limit,
                        verifier_id=last_verifier_id,
                        session=session
                    )
                    await add_verification_limit(
                        verification_logs=verification_logs_of_last_verifier,
                        verification_entries_statistics=verification_entries_statistics
                    )
                await sub_verification_limit(
                    verification_logs=verification_logs_of_verifier_without_team,
                    verification_entries_statistics=verification_entries_statistics_with_new
                )
                await change_verifier_in_verification_entries(
                    verifier_id=verifier_id_without_team,
                    verification_entries=act_number_entry.verification,
                    session=session,
                    company_id=company_id
                )
                await session.flush()
                return verifier_id_without_team

    # Проверка поверителей из других команд(не team_id и не None) и без поверителя по умолчанию

    teams: List[TeamModel] = await get_teams_with_verifiers_without_employee_verifier_team(
        team_id=team_id,
        company_id=company_id,
        session=session
    )

    for team in teams:
        for verifier_in_teams in team.verifiers:
            if not check_verifier_equipment(verifier_in_teams):
                continue

            verifier_id_in_teams: int = verifier_in_teams.id

            verification_logs_of_verifier_in_teams = await get_verification_logs_of_verifier(
                verification_dates=verification_entries_statistics_with_new.keys(),
                verification_limit=verification_limit,
                verifier_id=verifier_id_in_teams,
                session=session
            )

            access_flag_to_create_entry = await true_false_access_to_create_entry_with_this_verifier(
                verification_logs=verification_logs_of_verifier_in_teams,
                verification_entries_statistics=verification_entries_statistics_with_new
            )

            if access_flag_to_create_entry:
                if last_verifier_ids == {verifier_id_in_teams}:
                    await sub_verification_limit(
                        verification_logs=verification_logs_of_verifier_in_teams,
                        verification_entries_statistics=Counter(
                            {verification_date: 1})
                    )
                    await session.flush()
                    return verifier_id_in_teams
                else:
                    for last_verifier_id in last_verifier_ids:
                        verification_logs_of_last_verifier = await get_verification_logs_of_verifier(
                            verification_dates=verification_entries_statistics.keys(),
                            verification_limit=verification_limit,
                            verifier_id=last_verifier_id,
                            session=session
                        )
                        await add_verification_limit(
                            verification_logs=verification_logs_of_last_verifier,
                            verification_entries_statistics=verification_entries_statistics
                        )
                    await sub_verification_limit(
                        verification_logs=verification_logs_of_verifier_in_teams,
                        verification_entries_statistics=verification_entries_statistics_with_new
                    )
                    await change_verifier_in_verification_entries(
                        verifier_id=verifier_id_in_teams,
                        verification_entries=act_number_entry.verification,
                        session=session,
                        company_id=company_id
                    )
                    await session.flush()
                    return verifier_id_in_teams

    raise HTTPException(
        status_code=404,
        detail="Лимит записей поверок на данную дату превышен."
    )
