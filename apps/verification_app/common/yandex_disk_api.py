import asyncio
from typing import List, TypedDict
import httpx
from core.exceptions import CustomHTTPException, APIError


class UploadFile(TypedDict):
    file_name: str
    file_extension: str
    file_bytes: bytes


class AsyncYandexDiskAPI:
    BASE_URL = "https://cloud-api.yandex.net/v1/disk"
    ROOT_DIR = "/ТЕСТОВАЯ_ПАПКА"

    # "/ПОВЕРКА__НЕ_УДАЛЯТЬ"

    def __init__(self, token: str, timeout: float = 10.0, connect_timeout: float = 5.0):
        self.client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={"Authorization": f"OAuth {token}"},
            timeout=httpx.Timeout(timeout, connect=connect_timeout),
            follow_redirects=True,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.client.aclose()

    async def _request(self, method: str, endpoint: str, **kwargs):
        try:
            r = await self.client.request(method, endpoint, **kwargs)
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            data = e.response.json() if e.response.content else {}
            msg = data.get("message", e.response.text)
            raise APIError(e.response.status_code, msg) from None
        except httpx.RequestError as e:
            raise APIError(0, str(e)) from None
        return None if r.status_code == 204 or not r.content else r.json()

    async def exists_directory(self, path: str) -> bool:
        try:
            d = await self._request("GET", "/resources", params={"path": path, "fields": "type"})
            return d and d.get("type") == "dir"
        except APIError as e:
            if e.status == 404:
                return False
            raise

    async def ensure_directory(self, path: str):
        segments = path.strip("/").split("/")
        cur = ""
        for s in segments:
            cur += "/" + s
            if not await self.exists_directory(cur):
                await self._request("PUT", "/resources", params={"path": cur})

    async def check_token(self) -> bool:
        try:
            await self._request("GET", "/resources", params={"path": "/"})
            return True
        except APIError:
            return False

    async def get_upload_href(self, path: str) -> str:
        d = await self._request("GET", "/resources/upload", params={"path": path, "overwrite": "true"})
        return d["href"]

    async def publish(self, path: str):
        try:
            await self._request("PUT", "/resources/publish", params={"path": path})
        except APIError as e:
            if e.status != 409:
                raise

    async def get_public_url(self, path: str) -> str:
        d = await self._request("GET", "/resources", params={"path": path, "fields": "public_url"})
        url = d.get("public_url") if d else None
        if not url:
            raise APIError(502, "public_url not found")
        return url


class VerificationYandexDiskAPI(AsyncYandexDiskAPI):
    async def ensure_verification_path(
        self,
        company_dir: str,
        employee_fio: str,
        date_dir: str,
        act_series: str,
        act_number: str
    ) -> str:
        p = (
            f"{self.ROOT_DIR}/{company_dir}/{employee_fio}/"
            f"{date_dir}/{act_series}/{act_number}"
        )
        await self.ensure_directory(p)
        return p

    async def delete_verification_files(
        self,
        company_id: int,
        company_dir: str,
        employee_fio: str,
        date_dir: str,
        act_series: str,
        act_number: str,
        file_names: List[str],
    ) -> None:
        base = await self.ensure_verification_path(
            company_dir, employee_fio, date_dir, act_series, act_number
        )

        async def _delete(name: str) -> None:
            try:
                await self._request("DELETE", "/resources", params={"path": f"{base}/{name}"})
            except APIError as e:
                if e.status != 404:
                    raise CustomHTTPException(
                        status_code=502,
                        company_id=company_id,
                        detail=f"Ошибка при удалении файла {name}: {e}",
                    )

        await asyncio.gather(*(_delete(n) for n in file_names))

    async def upload_verification_files(
        self,
        company_dir: str,
        employee_fio: str,
        date_dir: str,
        act_series: str,
        act_number: str,
        files: List[UploadFile],
        concurrency: int = 5,
    ) -> List[str]:
        base = await self.ensure_verification_path(
            company_dir, employee_fio, date_dir, act_series, act_number
        )
        concurrency = concurrency or len(files)
        sem = asyncio.Semaphore(concurrency)

        async def _upload(idx: int, f: UploadFile) -> str:
            async with sem:
                filename = f"{idx}.{f['file_extension']}"
                path = f"{base}/{filename}"
                href = await self.get_upload_href(path)
                await self.client.put(href, content=f["file_bytes"])
                await self.publish(path)
                return await self.get_public_url(path)

        return await asyncio.gather(*(_upload(i, f) for i, f in enumerate(files, 1)))
