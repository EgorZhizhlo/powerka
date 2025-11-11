from apps.tariff_app.features.company_tariffs.api import (
    company_tariffs_api_router
)
from apps.tariff_app.features.company_tariffs.frontend import (
    company_tariffs_frontend_router
)


__all__ = [
    "company_tariffs_api_router",
    "company_tariffs_frontend_router",
]
