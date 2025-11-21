from typing import List
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from infrastructure.yandex_disk.service import get_yandex_service

from models import ActNumberPhotoModel

from core.exceptions.api import BadRequestError


async def process_act_number_photos(
    session: AsyncSession,
    act_number_id: int,
    company_name: str,
    employee_fio: str,
    verification_date,
    act_series: str,
    act_number: int,
    token: str,
    new_images: List[UploadFile],
    deleted_images_id: List[int]
) -> int:
    """
    Полная обработка фотографий акта:
    - Удаление выбранных фото (БД + Яндекс.Диск)
    - Загрузка новых фото
    - Сохранение новых записей в БД

    Все параметры для пути и доступа передаются напрямую.
    """
    if not token:
        raise BadRequestError(
            detail="Не настроен токен Яндекс.Диска!"
        )

    if deleted_images_id:
        q = select(ActNumberPhotoModel).where(
            ActNumberPhotoModel.id.in_(deleted_images_id),
            ActNumberPhotoModel.act_number_id == act_number_id
        )
        photos_to_delete = (await session.scalars(q)).all()

        file_names = [p.file_name for p in photos_to_delete]

        # Удаление с Яндекса
        if file_names:
            async with get_yandex_service(token) as yandex:
                await yandex.delete_verification_files(
                    company_name=company_name,
                    employee_fio=employee_fio,
                    verification_date=verification_date,
                    act_series=act_series,
                    act_number=act_number,
                    file_names=file_names,
                    permanently=True
                )

        # Удаление из базы
        await session.execute(
            delete(ActNumberPhotoModel).where(
                ActNumberPhotoModel.id.in_(deleted_images_id)
            )
        )

    new_images = [f for f in new_images if getattr(f, "filename", "").strip()]
    if not new_images:
        return 0

    async with get_yandex_service(token) as yandex:
        result = await yandex.upload_images_batch(
            files=new_images,
            company_name=company_name,
            employee_fio=employee_fio,
            verification_date=verification_date,
            act_series=act_series,
            act_number=act_number
        )

    uploaded_files = result.get("files", [])

    for filename, url in uploaded_files:
        session.add(
            ActNumberPhotoModel(
                act_number_id=act_number_id,
                file_name=filename,
                url=url
            )
        )

    return len(uploaded_files)
