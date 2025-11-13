import os
import httpx
from typing import Any, Dict
from core.exceptions import CustomHTTPException


class AsyncYandexDiskAPI:
    BASE_URL = "https://cloud-api.yandex.net/v1/disk"
    NAME_BASE_DIR = "/ТЕСТОВАЯ_ПАПКА"
    # "/ПОВЕРКА__НЕ_УДАЛЯТЬ"

    def __init__(self, token: str):
        """
        :param token: OAuth‑токен.
        """
        self.token = token
        self.headers = {"Authorization": f"OAuth {self.token}"}

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Dict[str, Any] = None,
        json: Dict[str, Any] = None,
        data: Any = None,
    ) -> Dict[str, Any]:
        url = f"{self.BASE_URL}{endpoint}"
        async with httpx.AsyncClient(headers=self.headers) as client:
            response = await client.request(
                method, url, params=params, json=json, content=data
            )
        if response.status_code >= 400:
            # выдергиваем либо сообщение из JSON, либо весь текст
            try:
                err_msg = response.json().get("message", response.text)
            except ValueError:
                err_msg = response.text
            raise RuntimeError(f"Ошибка {response.status_code} {method} {url}: {err_msg}")
        # 204 — нет тела
        if response.status_code == 204:
            return {}
        return response.json()

    async def exists_directory(self, path: str) -> bool:
        """
        Проверить, существует ли директория по полному пути.
        """
        try:
            data = await self._request("GET", "/resources", params={"path": path})
            return data.get("type") == "dir"
        except RuntimeError as e:
            # если 404 — директория не найдена
            if "Ошибка 404" in str(e):
                return False
            raise

    async def ensure_directory(self, path: str) -> None:
        """
        Рекурсивно создать папку и все её родительские,
        если их нет. Например: "/ПОВЕРКА__НЕ_УДАЛЯТЬ/Company|1".
        """
        # Нормализуем: один ведущий slash, без завершающего
        normalized = "/" + path.strip("/")
        segments = normalized.strip("/").split("/")
        current = ""
        for segment in segments:
            current += "/" + segment
            if not await self.exists_directory(current):
                # создаём именно эту папку
                await self._request("PUT", "/resources", params={"path": current})

    async def check_token(self) -> bool:
        """
        Проверить, валиден ли OAuth‑токен.
        """
        try:
            # простая проверка доступа к корню
            await self._request("GET", "/resources", params={"path": "/"})
            return True
        except RuntimeError:
            return False

    async def exists_company_directory(self, company_dir_name: str) -> bool:
        """
        Проверить, существует ли директория компании.
        """
        path = f"{self.NAME_BASE_DIR}/{company_dir_name}"
        return await self.exists_directory(path)

    async def create_company_directory(self, company_dir_name: str) -> None:
        """
        Создать директорию компании (с гарантией,
        что базовая папка тоже будет создана).
        """
        path = f"{self.NAME_BASE_DIR}/{company_dir_name}"
        await self.ensure_directory(path)

    async def rename_company_directory(
        self, old_company_dir_name: str, new_company_dir_name: str
    ) -> None:
        """
        Переименовать папку компании, при этом
        создавая новую базовую папку при необходимости.
        """
        old_path = f"{self.NAME_BASE_DIR}/{old_company_dir_name}"
        new_path = f"{self.NAME_BASE_DIR}/{new_company_dir_name}"

        parent = os.path.dirname(new_path)
        await self.ensure_directory(parent)

        params = {"from": old_path, "path": new_path}
        await self._request("POST", "/resources/move", params=params)


async def action_with_ya_disk(
    token: str, company_id: int,
    old_company_name: str, new_company_name: str
):
    api = AsyncYandexDiskAPI(token)
    if not await api.check_token():
        raise CustomHTTPException(
            status_code=404,
            detail=(
                "Токен Яндекс Диск не валиден! "
                "Попробуйте другой токен или оставьте поле пустым!"
            ),
            company_id=company_id,
        )

    old_exists = await api.exists_company_directory(old_company_name)
    new_exists = await api.exists_company_directory(new_company_name)

    if old_company_name and new_company_name and old_company_name != new_company_name:
        if old_exists:
            await api.rename_company_directory(
                old_company_name, new_company_name)
        else:
            await api.create_company_directory(new_company_name)
    else:
        if not new_exists:
            await api.create_company_directory(new_company_name)
