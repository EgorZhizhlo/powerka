import os
import tempfile
import asyncio
from typing import List
from datetime import date
from fastapi import UploadFile, HTTPException
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from core.config import settings

from infrastructure.yandex_disk.client import YandexDiskClient
from infrastructure.yandex_disk.schemas import (
    OperationMetadata, DocumentMetadata, FileInfo
)


class YandexDiskService:
    """Сервис для работы с Yandex Disk."""

    ROOT_PATH = '/ХРАНИЛИЩЕ_ДЛЯ_ПОВЕРКИ_НЕ_УДАЛЯТЬ'

    def __init__(self, token: str = None, timeout: int = 120):
        self.client = YandexDiskClient(
            token=token,
            timeout=timeout
        )
        self._executor = ThreadPoolExecutor(max_workers=2)

    @staticmethod
    def _cleanup_temp_file(tmp_path: str) -> None:
        """Синхронная очистка временного файла."""
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    async def startup(self):
        """Инициализация клиента."""
        await self.client.startup()

    async def shutdown(self):
        """Закрытие клиента."""
        await self.client.shutdown()
        self._executor.shutdown(wait=False)

    def _build_path_from_metadata(self, metadata: OperationMetadata) -> str:
        """
        Построение пути из метаданных.
        Останавливается на первом None параметре.
        Структура: /BASE/Компания/ФИО/Дата/Серия/Номер
        """
        path = self.ROOT_PATH

        # Компания
        if metadata.company_name is None:
            return path
        path = f"{path}/{metadata.company_name}"

        # ФИО
        if metadata.employee_fio is None:
            return path
        path = f"{path}/{metadata.employee_fio}"

        # Дата
        if metadata.verification_date is None:
            return path
        date_str = metadata.verification_date.strftime("%Y.%m.%d")
        path = f"{path}/{date_str}"

        # Серия
        if metadata.act_series is None:
            return path
        path = f"{path}/{metadata.act_series}"

        # Номер
        if metadata.act_number is None:
            return path
        path = f"{path}/{metadata.act_number}"

        return path

    async def _ensure_folder_exists(self, folder_path: str) -> None:
        """Создание всей иерархии папок."""
        if await self.client.folder_exists(folder_path):
            return

        # Создаем все родительские папки
        parts = [p for p in folder_path.split('/') if p]

        paths_to_create = []
        for i in range(1, len(parts) + 1):
            path = '/' + '/'.join(parts[:i])
            paths_to_create.append(path)

        for path in paths_to_create:
            try:
                await self.client.create_folder(path)
            except Exception:
                pass

    def _validate_image(self, file: UploadFile) -> None:
        """Валидация типа файла изображения."""
        if file.content_type not in settings.allowed_image_formats:
            raise HTTPException(
                status_code=400,
                detail=f"Недопустимый формат: {file.content_type}. "
                f"Разрешены: {', '.join(settings.allowed_image_formats)}"
            )

    async def _validate_file_size(self, file: UploadFile) -> None:
        """Валидация размера файла (максимум 5 МБ)."""
        # Читаем файл чтобы узнать реальный размер
        content = await file.read()
        file_size = len(content)

        # Возвращаем указатель в начало для последующего чтения
        await file.seek(0)

        if file_size > settings.image_max_size_mb:
            size_mb = file_size / (1024 * 1024)
            max_mb = settings.image_max_size_mb / (1024 * 1024)
            raise HTTPException(
                status_code=400,
                detail=f"Файл '{file.filename}' слишком большой: "
                f"{size_mb:.2f} МБ. Максимум: {max_mb:.0f} МБ"
            )

    @staticmethod
    def _save_temp_file(content: bytes, suffix: str) -> str:
        """Синхронное сохранение во временный файл."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            return tmp.name

    async def create_folder_from_metadata(
        self, metadata: OperationMetadata
    ) -> str:
        folder_path = self._build_path_from_metadata(metadata)
        await self._ensure_folder_exists(folder_path)
        return folder_path

    async def rename_resource(
        self,
        metadata: OperationMetadata,
        new_company_name: str = None,
        new_employee_fio: str = None,
        new_document_date: date = None,
        new_act_series: str = None,
        new_act_number: str = None
    ) -> dict:
        """Переименование любого компонента пути."""
        old_path = self._build_path_from_metadata(metadata)

        if not await self.client.folder_exists(old_path):
            raise HTTPException(
                status_code=404,
                detail=f"Ресурс не найден: {old_path}"
            )

        # Определяем какой компонент переименовываем
        rename_count = sum([
            new_company_name is not None,
            new_employee_fio is not None,
            new_document_date is not None,
            new_act_series is not None,
            new_act_number is not None
        ])

        if rename_count != 1:
            raise HTTPException(
                status_code=400,
                detail="Укажите ровно один компонент для переименования"
            )

        # Строим новый путь
        if new_company_name:
            # Переименовываем компанию
            parent = old_path.rsplit("/", 1)[0]
            new_path = f"{parent}/{new_company_name}"
        elif new_employee_fio:
            # Переименовываем ФИО
            parts = old_path.rsplit("/", 1)
            parent_parts = parts[0].rsplit("/", 1)
            new_path = f"{parent_parts[0]}/{new_employee_fio}/{parts[1]}"
        elif new_document_date:
            # Переименовываем дату
            date_str = new_document_date.strftime("%Y-%m-%d")
            parts = old_path.rsplit("/", 1)
            parent_parts = parts[0].rsplit("/", 1)
            new_path = f"{parent_parts[0]}/{date_str}/{parts[1]}"
        elif new_act_series:
            # Переименовываем серию
            parts = old_path.rsplit("/", 1)
            parent_parts = parts[0].rsplit("/", 1)
            new_path = f"{parent_parts[0]}/{new_act_series}/{parts[1]}"
        elif new_act_number:
            # Переименовываем номер
            parent = old_path.rsplit("/", 1)[0]
            new_path = f"{parent}/{new_act_number}"

        await self.client.move(old_path, new_path, overwrite=False)

        return {
            "success": True,
            "old_path": old_path,
            "new_path": new_path
        }

    async def delete_resource(
        self,
        company_name: str | None = None,
        employee_fio: str | None = None,
        verification_date: date | None = None,
        act_series: str | None = None,
        act_number: str | None = None,
        permanently: bool = True
    ) -> dict:
        """
        Удаление ресурса по переданным полям акта.
        """

        metadata = OperationMetadata(
            company_name=company_name,
            employee_fio=employee_fio,
            verification_date=verification_date,
            act_series=act_series,
            act_number=act_number
        )

        path = self._build_path_from_metadata(metadata)

        if not await self.client.folder_exists(path):
            raise HTTPException(
                status_code=404,
                detail=f"Ресурс не найден: {path}"
            )

        await self.client.delete(path, permanently=permanently)

        return {
            "success": True,
            "path": path,
            "permanently": permanently
        }

    async def create_company_folder(self, company_name: str):
        metadata = OperationMetadata(company_name=company_name)
        path = self._build_path_from_metadata(metadata)

        await self._ensure_folder_exists(path)

    async def rename_company_folder(
            self, old_company_name: str, new_company_name: str
    ) -> dict:
        meta = OperationMetadata(company_name=old_company_name)
        return await self.rename_resource(
            metadata=meta,
            new_company_name=new_company_name
        )

    async def ensure_company_folder(
        self,
        new_company_name: str,
        old_company_name: str | None = None
    ):
        new_meta = OperationMetadata(company_name=new_company_name)
        new_path = self._build_path_from_metadata(new_meta)

        if old_company_name:
            old_meta = OperationMetadata(company_name=old_company_name)
            old_path = self._build_path_from_metadata(old_meta)

            if await self.client.folder_exists(old_path):
                if old_company_name != new_company_name:
                    await self.client.move(old_path, new_path, overwrite=False)
                return

        await self._ensure_folder_exists(new_path)

    async def delete_verification_files(
        self,
        company_name: str,
        employee_fio: str,
        verification_date: date,
        act_series: str,
        act_number: str,
        file_names: List[str],
        permanently: bool = True
    ):
        """
        Удаление отдельных файлов по полям акта проверки.
        Сервис сам собирает metadata и удаляет файлы.
        """
        metadata = OperationMetadata(
            company_name=company_name,
            employee_fio=employee_fio,
            verification_date=verification_date,
            act_series=act_series,
            act_number=act_number
        )

        base_path = self._build_path_from_metadata(metadata)

        for name in file_names:
            file_path = f"{base_path}/{name}"

            try:
                await self.client.delete(file_path, permanently=permanently)
            except Exception:
                # Пропускаем если файл отсутствует
                pass

        return {"success": True, "deleted": file_names}

    async def upload_images_batch(
        self,
        files: List[UploadFile],
        company_name: str,
        employee_fio: str,
        verification_date: date,
        act_series: str,
        act_number: str
    ) -> dict:
        """
        Пакетная загрузка изображений.

        Args:
            files: Список файлов для загрузки (до 15 штук)
            company_name: Название компании
            employee_fio: ФИО сотрудника
            verification_date: Дата документа
            act_series: Серия акта
            act_number: Номер акта

        Returns:
            dict с информацией о загруженных файлах
        """
        metadata = OperationMetadata(
            company_name=company_name,
            employee_fio=employee_fio,
            verification_date=verification_date,
            act_series=act_series,
            act_number=act_number
        )

        # Валидация количества файлов
        if len(files) > settings.image_limit_per_verification:
            raise HTTPException(
                status_code=400,
                detail=f"Максимальное количество файлов: {settings.image_limit_per_verification}"
            )

        for file in files:
            self._validate_image(file)
            await self._validate_file_size(file)

        # Построение пути к папке
        folder_path = self._build_path_from_metadata(metadata)

        # Создание структуры папок
        await self._ensure_folder_exists(folder_path)

        occupied: set[int] = await self.client.get_existing_file_indices(folder_path)
        all_slots = set(range(1, settings.image_limit_per_verification + 1))
        free_slots = sorted(all_slots - occupied)

        if len(free_slots) < len(files):
            raise HTTPException(
                status_code=400,
                detail=f"В папке уже {len(occupied)} файлов. "
                f"Максимум {settings.image_limit_per_verification} файлов на папку. "
                f"Можно загрузить ещё {len(free_slots)}."
            )

        assigned_indices = free_slots[:len(files)]

        uploaded: List[tuple] = []
        failed: List[str] = []

        semaphore = asyncio.Semaphore(3)

        async def upload_one(file: UploadFile, slot: int):
            async with semaphore:
                tmp_file = None
                try:
                    content = await file.read()
                    await file.seek(0)

                    loop = asyncio.get_running_loop()
                    ext = os.path.splitext(file.filename)[1]

                    tmp_file = await loop.run_in_executor(
                        self._executor,
                        self._save_temp_file,
                        content,
                        ext
                    )

                    final_name = f"{slot:03d}{ext}"
                    remote_path = f"{folder_path}/{final_name}"

                    await self.client.upload_file(tmp_file, remote_path)

                    try:
                        await self.client.publish(remote_path)
                        url = await self.client.get_public_url(remote_path)
                    except Exception:
                        url = None

                    uploaded.append((final_name, url))

                except Exception:
                    failed.append(file.filename)

                finally:
                    if tmp_file:
                        loop.create_task(
                            loop.run_in_executor(
                                self._executor,
                                self._cleanup_temp_file,
                                tmp_file
                            )
                        )

        await asyncio.gather(
            *(upload_one(f, slot) for f, slot in zip(files, assigned_indices))
        )

        return {
            "success": len(failed) == 0,
            "files": uploaded
        }


@asynccontextmanager
async def get_yandex_service(token: str):
    service = YandexDiskService(token=token)
    await service.startup()
    try:
        yield service
    finally:
        await service.shutdown()
