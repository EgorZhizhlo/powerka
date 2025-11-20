from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from typing import Any

from core.exceptions.base import (
    ApiHttpException,
    FrontendHttpException,
    AppHttpException,
    RedirectHttpException
)
from access_control.middlewares import (
    AuthMiddleware,
    TariffMiddleware
)

from apps import (
    auth_router,
    calendar_router,
    company_router,
    verification_router,
    tariff_router,
    webhook_router,
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
    docs_url="/test/docs", redoc_url="/test/redocs",
    lifespan=lifespan,
    # servers=[{"url": "https://powerka.pro"}]
)
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
app.add_middleware(TariffMiddleware)
app.add_middleware(AuthMiddleware)

app.include_router(auth_router, tags=["Авторизация"])
app.include_router(calendar_router, tags=["Календарь"])
app.include_router(company_router, tags=["Меню компаний"])
app.include_router(verification_router, tags=["Поверка"])
app.include_router(tariff_router, tags=["Тарифы компаний"])
app.include_router(webhook_router, tags=["Вебхуки"])

templates = Jinja2Templates(directory="templates")


@app.exception_handler(AppHttpException)
async def app_http_exception_handler(
    request: Request, exc: AppHttpException
) -> Any:
    if "/api/" in request.url.path:
        content = {"detail": exc.detail or "Ошибка доступа"}
        return JSONResponse(status_code=exc.status_code, content=content)

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


@app.exception_handler(ApiHttpException)
async def api_http_exception_handler(
    request: Request, exc: ApiHttpException
) -> JSONResponse:
    content = {"detail": exc.detail or "Ошибка доступа"}
    return JSONResponse(
        status_code=exc.status_code, content=content
    )


@app.exception_handler(FrontendHttpException)
async def frontend_http_exception_handler(
    request: Request, exc: FrontendHttpException
) -> Any:
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


@app.exception_handler(RedirectHttpException)
async def redirect_http_exception_handler(
    request: Request, exc: RedirectHttpException
) -> RedirectResponse:
    redirect_url = getattr(exc, "redirect_url", "/")
    return RedirectResponse(
        status_code=303, url=redirect_url
    )
