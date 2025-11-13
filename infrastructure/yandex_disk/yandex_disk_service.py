import os
import tempfile
import asyncio
from typing import List
from datetime import date
from fastapi import UploadFile, HTTPException
from concurrent.futures import ThreadPoolExecutor

from app.modules.yandex_disk_client import YandexDiskClient
from app.modules.schemas import DocumentMetadata, FileInfo, OperationMetadata

from app.core.config import settings


class YandexDiskService:
    """Сервис для работы с Yandex Disk."""

    def __init__(self, token: str = None, timeout: int = 120):
        self.client = YandexDiskClient(
            token=token,
            timeout=timeout
        )
        self.base_path = '/ПОВЕРКА_НЕ_УДАЛЯТЬ'
        self._executor = ThreadPoolExecutor(max_workers=2)

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
        path = self.base_path

        # Компания
        if metadata.company_name is None:
            return path
        path = f"{path}/{metadata.company_name}"

        # ФИО
        if metadata.employee_fio is None:
            return path
        path = f"{path}/{metadata.employee_fio}"

        # Дата
        if metadata.document_date is None:
            return path
        date_str = metadata.document_date.strftime("%Y-%m-%d")
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

    @staticmethod
    def _cleanup_temp_file(tmp_path: str) -> None:
        """Синхронная очистка временного файла."""
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    def _build_folder_path(self, metadata: DocumentMetadata) -> str:
        """
        Построение иерархической структуры папок для загрузки.
        Структура: /BASE/Компания/ФИО/Дата/Серия/Номер
        """
        date_str = metadata.document_date.strftime("%Y-%m-%d")

        folder_path = (
            f"{self.base_path}/"
            f"{metadata.company_name}/"
            f"{metadata.employee_fio}/"
            f"{date_str}/"
            f"{metadata.act_series}/"
            f"{metadata.act_number}"
        )

        return folder_path

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

    async def upload_images_batch(
        self,
        files: List[UploadFile],
        metadata: DocumentMetadata
    ) -> dict:
        """
        Пакетная загрузка изображений.

        Args:
            files: Список файлов для загрузки (до 15 штук)
            metadata: Метаданные для структурирования хранения

        Returns:
            dict с информацией о загруженных файлах
        """
        # Валидация количества файлов
        if len(files) > settings.image_limit_per_verification:
            raise HTTPException(
                status_code=400,
                detail=f"Максимальное количество файлов: {settings.image_limit_per_verification}"
            )

        # Валидация типов файлов
        for file in files:
            self._validate_image(file)

        # Валидация размеров файлов
        for file in files:
            await self._validate_file_size(file)

        # Построение пути к папке
        folder_path = self._build_folder_path(metadata)

        # Создание структуры папок
        await self._ensure_folder_exists(folder_path)

        # Получаем уже занятые индексы файлов в папке
        existing_indices = await self.client.get_existing_file_indices(folder_path)

        # Проверяем лимит: не более 15 файлов в папке
        if len(existing_indices) + len(files) > settings.image_limit_per_verification:
            raise HTTPException(
                status_code=400,
                detail=f"В папке уже {len(existing_indices)} файлов. "
                f"Максимум {settings.image_limit_per_verification} файлов на папку. "
                f"Можно загрузить ещё {settings.image_limit_per_verification - len(existing_indices)}."
            )

        # Генерируем новые индексы для файлов (дозаписываем после существующих)
        next_index = max(existing_indices) + 1 if existing_indices else 1
        file_indices = list(range(next_index, next_index + len(files)))

        # Результаты загрузки
        uploaded_files: List[FileInfo] = []
        failed_files: List[dict] = []

        # Семафор для ограничения параллельных загрузок
        semaphore = asyncio.Semaphore(3)  # Не более 3 одновременно

        async def upload_single_file(file: UploadFile, index: int):
            async with semaphore:
                tmp_file = None
                try:
                    # Читаем содержимое файла
                    content = await file.read()
                    try:
                        await file.seek(0)
                    except Exception:
                        pass

                    # Сохраняем во временный файл (в executor)
                    loop = asyncio.get_running_loop()
                    tmp_file = await loop.run_in_executor(
                        self._executor,
                        self._save_temp_file,
                        content,
                        os.path.splitext(file.filename)[1]
                    )

                    # Получаем размер в executor
                    file_size = await loop.run_in_executor(
                        self._executor,
                        os.path.getsize,
                        tmp_file
                    )

                    # Формируем имя файла с оригинальным расширением
                    base_name = os.path.splitext(file.filename)[0]
                    ext = os.path.splitext(file.filename)[1]
                    final_filename = f"{index:03d}_{base_name}{ext}"
                    remote_path = f"{folder_path}/{final_filename}"

                    # Загружаем на Yandex Disk
                    await self.client.upload_file(tmp_file, remote_path)

                    # Публикуем файл
                    try:
                        await self.client.publish(remote_path)
                        public_url = await self.client.get_public_url(remote_path)
                    except Exception:
                        public_url = None

                    uploaded_files.append(FileInfo(
                        filename=final_filename,
                        original_filename=file.filename,
                        remote_path=remote_path,
                        public_url=public_url,
                        size_bytes=file_size,
                        compressed=False
                    ))

                except Exception as e:
                    failed_files.append({
                        "filename": file.filename,
                        "error": str(e)
                    })
                finally:
                    # Очистка временного файла
                    if tmp_file:
                        loop = asyncio.get_running_loop()
                        loop.create_task(
                            loop.run_in_executor(
                                self._executor,
                                self._cleanup_temp_file,
                                tmp_file
                            )
                        )

        # Загружаем все файлы асинхронно с правильными индексами
        tasks = [
            upload_single_file(file, file_indices[i])
            for i, file in enumerate(files)
        ]
        await asyncio.gather(*tasks)

        return {
            "success": len(failed_files) == 0,
            "uploaded_files": uploaded_files,
            "failed_files": failed_files,
            "total_files": len(files),
            "successful_uploads": len(uploaded_files),
            "folder_path": folder_path
        }

    async def move_files(
        self,
        source_metadata: OperationMetadata,
        destination_metadata: OperationMetadata,
        merge: bool = False
    ) -> dict:
        """
        Перенос файлов между папками по метаданным.
        """
        source_path = self._build_path_from_metadata(source_metadata)
        destination_path = self._build_path_from_metadata(destination_metadata)

        if not await self.client.folder_exists(source_path):
            raise HTTPException(
                status_code=404,
                detail=f"Исходная папка не найдена: {source_path}"
            )

        if not merge:
            await self.client.move(
                source_path, destination_path, overwrite=True
            )
            return {
                "success": True,
                "source_path": source_path,
                "destination_path": destination_path,
                "message": "Папка успешно перенесена"
            }

        await self._ensure_folder_exists(destination_path)
        meta = await self.client.get_meta(source_path)
        items = meta.get("_embedded", {}).get("items", [])

        for item in items:
            item_name = item["name"]
            src = f"{source_path}/{item_name}"
            dst = f"{destination_path}/{item_name}"
            try:
                await self.client.move(src, dst, overwrite=True)
            except Exception:
                pass

        try:
            await self.client.delete(source_path, permanently=False)
        except Exception:
            pass

        return {
            "success": True,
            "source_path": source_path,
            "destination_path": destination_path,
            "message": "Файлы успешно объединены"
        }

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
        metadata: OperationMetadata,
        permanently: bool = True
    ) -> dict:
        """Удаление по метаданным."""
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

    async def get_folder_contents(self, metadata: OperationMetadata) -> dict:
        """Получение содержимого папки по метаданным."""
        path = self._build_path_from_metadata(metadata)

        if not await self.client.folder_exists(path):
            raise HTTPException(
                status_code=404,
                detail=f"Папка не найдена: {path}"
            )

        meta = await self.client.get_meta(path)
        items = meta.get("_embedded", {}).get("items", [])

        return {
            "path": path,
            "items": items,
            "total_items": len(items)
        }


# Глобальный экземпляр сервиса
yandex_disk_service = YandexDiskService()
