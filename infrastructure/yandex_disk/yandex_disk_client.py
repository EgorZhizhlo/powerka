import aiohttp
import asyncio
import urllib.parse
from typing import Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor


class YandexDiskClient:
    BASE_URL = "https://cloud-api.yandex.net/v1/disk"

    def __init__(self, token: str, timeout: int = 30):
        self.token = token
        self.headers = {"Authorization": f"OAuth {token}"}
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.session: Optional[aiohttp.ClientSession] = None
        # Уменьшаем потоки так как нет сжатия
        self._executor = ThreadPoolExecutor(max_workers=2)

    async def startup(self):
        """Call this once on FastAPI startup event."""
        if not self.session:
            self.session = aiohttp.ClientSession(timeout=self.timeout)

    async def shutdown(self):
        """Call this once on FastAPI shutdown event."""
        if self.session:
            await self.session.close()
        self._executor.shutdown(wait=False)

    # =====================================================================================
    # Internal helpers
    # =====================================================================================

    async def _request(self, method: str, url: str, retries: int = 5, **kwargs) -> Dict[str, Any]:
        """Common HTTP wrapper with retry, 202 async operations and proper error handling."""
        if not self.session:
            await self.startup()

        for attempt in range(retries + 1):
            async with self.session.request(method, url, headers=self.headers, **kwargs) as resp:

                # Too many requests or resource is locked
                if resp.status in (423, 429):
                    if attempt == retries:
                        raise Exception(
                            "Too many retries (423/429) from YandexDisk")
                    await asyncio.sleep(0.3 * (attempt + 1))
                    continue

                # Async operation → poll
                if resp.status == 202:
                    payload = await resp.json()
                    # Яндекс может вернуть href или operation_id
                    operation_url = payload.get("href")
                    if operation_url:
                        return await self._poll_operation_status_by_url(
                            operation_url
                        )
                    op_id = payload.get("operation_id")
                    if op_id:
                        return await self._poll_operation_status(op_id)
                    # Если нет ни того ни другого - считаем успехом
                    return {"success": True}

                # No content OK
                if resp.status == 204:
                    return {"success": True}

                # Try parse JSON
                try:
                    data = await resp.json()
                except Exception:
                    data = {"raw": await resp.text()}

                # Error status
                if resp.status >= 400:
                    raise Exception(f"YandexDisk error {resp.status}: {data}")

                return data

        raise Exception("Unexpected request exit")

    async def _poll_operation_status(self, operation_id: str):
        """Poll async operation until finished."""
        url = f"{self.BASE_URL}/operations/{operation_id}"
        return await self._poll_operation_status_by_url(url)

    async def _poll_operation_status_by_url(self, url: str):
        """Poll async operation by URL until finished."""
        for _ in range(120):  # max ~1 minute
            async with self.session.get(url, headers=self.headers) as resp:
                # Если 404 - операция завершена и удалена
                if resp.status == 404:
                    return {"success": True}

                data = await resp.json()
                status = data.get("status")

                if status == "success":
                    return {"success": True}
                if status == "failed":
                    raise Exception(f"Operation failed: {data}")

            await asyncio.sleep(0.5)

        raise Exception("Operation timeout")

    @staticmethod
    def _encode(path: str) -> str:
        return urllib.parse.quote(path, safe="/")

    # =====================================================================================
    # Public API
    # =====================================================================================

    async def create_folder(self, path: str):
        url = f"{self.BASE_URL}/resources?path={self._encode(path)}"
        return await self._request("PUT", url)

    async def folder_exists(self, path: str) -> bool:
        """Проверка существования ресурса (файла или папки)."""
        try:
            await self.get_meta(path)
            return True
        except Exception:
            return False

    async def get_meta(self, path: str):
        url = f"{self.BASE_URL}/resources?path={self._encode(path)}"
        return await self._request("GET", url)

    # =====================================================================================
    # Uploading
    # =====================================================================================

    async def _get_upload_url(self, path: str, overwrite=True) -> str:
        url = (f"{self.BASE_URL}/resources/upload?"
               f"path={self._encode(path)}&overwrite={'true' if overwrite else 'false'}")
        data = await self._request("GET", url)
        return data["href"]

    async def upload_file(self, local_path: str, remote_path: str):
        """Загрузка файла на Yandex Disk (асинхронно)."""
        upload_url = await self._get_upload_url(remote_path)

        if not self.session:
            await self.startup()

        # Читаем файл в executor чтобы не блокировать event loop
        def read_file_sync():
            with open(local_path, "rb") as f:
                return f.read()

        loop = asyncio.get_event_loop()
        file_data = await loop.run_in_executor(
            self._executor,
            read_file_sync
        )

        async with self.session.put(
            upload_url, data=file_data, headers=None
        ) as resp:
            if resp.status not in (200, 201, 202):
                text = await resp.text()
                raise Exception(f"Upload failed: {resp.status}, {text}")

        return {"success": True}

    # =====================================================================================
    # Publishing
    # =====================================================================================

    async def publish(self, path: str):
        url = f"{self.BASE_URL}/resources/publish?path={self._encode(path)}"
        return await self._request("PUT", url)

    async def get_public_url(self, path: str) -> Optional[str]:
        meta = await self.get_meta(path)
        return meta.get("public_url")

    # =====================================================================================
    # Move / Rename
    # =====================================================================================

    async def move(self, old_path: str, new_path: str, overwrite=True):
        url = (f"{self.BASE_URL}/resources/move?"
               f"from={self._encode(old_path)}"
               f"&path={self._encode(new_path)}"
               f"&overwrite={'true' if overwrite else 'false'}")
        return await self._request("POST", url)

    async def rename(self, path: str, new_name: str):
        parent = path.rsplit("/", 1)[0]
        new_path = f"{parent}/{new_name}"
        return await self.move(path, new_path)

    # =====================================================================================
    # Listing
    # =====================================================================================

    async def list_folder(self, path: str, limit: int = 1000) -> list:
        """
        Получить список файлов в папке.

        Returns:
            Список элементов или пустой список если папка не существует
        """
        try:
            meta = await self.get_meta(path)
            items = meta.get("_embedded", {}).get("items", [])
            return items[:limit]
        except Exception:
            # Папка не существует или нет прав доступа
            return []

    async def get_existing_file_indices(self, folder_path: str) -> set:
        """
        Получить множество уже занятых индексов файлов в папке.

        Парсит имена файлов формата "001_filename.jpg" и возвращает
        множество занятых числовых индексов.
        """
        items = await self.list_folder(folder_path)
        indices = set()

        for item in items:
            if item.get("type") != "file":
                continue

            name = item.get("name", "")
            if not name or "_" not in name:
                continue

            # Парсим имя формата "001_filename.jpg"
            try:
                index_str = name.split("_", 1)[0]
                index = int(index_str)
                indices.add(index)
            except (ValueError, IndexError):
                continue

        return indices

    # =====================================================================================
    # Deleting
    # =====================================================================================

    async def delete(self, path: str, permanently=True):
        """
        Удалить ресурс (файл или папку).

        Args:
            path: Путь к ресурсу
            permanently: True - удалить навсегда, False - в корзину
        """
        url = (f"{self.BASE_URL}/resources?"
               f"path={self._encode(path)}"
               f"&permanently={'true' if permanently else 'false'}"
               f"&force_async=false")
        return await self._request("DELETE", url)
