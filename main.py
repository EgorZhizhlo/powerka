from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from core.exceptions import CustomHTTPException
from access_control.middlewares import (
    AuthMiddleware,
    TariffMiddleware
)

from apps import (
    auth_router,
    calendar_router,
    company_router,
    verification_router,
    tariff_router
)

from infrastructure.cache import init_redis, close_redis
from infrastructure.db.session import init_db, close_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    await init_redis()
    yield
    # Shutdown
    await close_redis()
    await close_db()


app = FastAPI(
    docs_url="/test/docs", redoc_url="/test/docs",
    lifespan=lifespan,
    # servers=[{"url": "https://powerka.pro"}]
)
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
app.add_middleware(TariffMiddleware)
app.add_middleware(AuthMiddleware)

app.include_router(auth_router)
app.include_router(calendar_router)
app.include_router(company_router)
app.include_router(verification_router)
app.include_router(tariff_router)

templates = Jinja2Templates(directory="templates")


@app.exception_handler(CustomHTTPException)
async def custom_http_exception_handler(
    request: Request, exc: CustomHTTPException
):
    if "/api/" in request.url.path:
        content = {"detail": exc.detail or "Ошибка доступа"}
        return JSONResponse(status_code=exc.status_code, content=content)

    # Если есть редирект
    if redirect_url := getattr(exc, "redirect_url", None):
        return RedirectResponse(status_code=303, url=redirect_url)

    # Иначе HTML-ответ
    return templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "status_code": exc.status_code,
            "error": exc.detail or "Неизвестная ошибка",
            "company_id": getattr(exc, "company_id", None),
        },
        status_code=exc.status_code,
    )
