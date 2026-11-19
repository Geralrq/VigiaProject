from fastapi import FastAPI

from app.shared.adapters.inbound.health import router as health_router


def create_app() -> FastAPI:
    """Composition root: the only place that wires concrete adapters."""
    app = FastAPI(title="Vigía API", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.include_router(health_router, prefix="/api")
    return app
