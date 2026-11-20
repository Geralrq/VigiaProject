"""Composition root: the only module that knows concrete adapters.

Each `provide_*` function is a FastAPI dependency. Routers receive providers as
arguments, so tests swap any of them via `app.dependency_overrides[provide_x]`.
"""

from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.monitoring.adapters.inbound.zones_router import build_zones_router
from app.monitoring.adapters.outbound.persistence.zone_repository import SqlAlchemyZoneRepository
from app.monitoring.application.ports.zone_repository import ZoneRepository
from app.monitoring.application.use_cases.create_zone import CreateZone
from app.monitoring.application.use_cases.list_zones import ListZones
from app.shared.adapters.inbound.health import router as health_router
from app.shared.adapters.inbound.problems import register_problem_handlers
from app.shared.adapters.inbound.security import build_auth_dependencies
from app.shared.adapters.outbound.auth.jwks_token_verifier import (
    JwksTokenVerifier,
    build_jwk_client,
)
from app.shared.adapters.outbound.persistence.engine import build_engine
from app.shared.adapters.outbound.persistence.profile_repository import (
    SqlAlchemyProfileRepository,
)
from app.shared.application.ports.auth import ProfileRepository, TokenVerifier
from app.shared.application.use_cases.authenticate_user import AuthenticateUser
from app.shared.settings import get_settings

CORS_ORIGINS = ["http://localhost:3000"]
JWT_AUDIENCE = "authenticated"


# --- infrastructure -------------------------------------------------------------------


@lru_cache
def _engine() -> Engine:
    return build_engine(get_settings().database_url.get_secret_value())


def provide_session() -> Iterator[Session]:
    """One transaction per request; commits before the response is sent."""
    with Session(_engine()) as session, session.begin():
        yield session


SessionDep = Annotated[Session, Depends(provide_session, scope="function")]


@lru_cache  # process-wide singleton: keeps the JWKS cache warm across requests
def provide_token_verifier() -> TokenVerifier:
    settings = get_settings()
    return JwksTokenVerifier(
        build_jwk_client(settings.jwks_url), audience=JWT_AUDIENCE, issuer=settings.jwt_issuer
    )


# --- shared: auth ---------------------------------------------------------------------


def provide_profile_repository(session: SessionDep) -> ProfileRepository:
    return SqlAlchemyProfileRepository(session)


def provide_authenticate_user(
    verifier: Annotated[TokenVerifier, Depends(provide_token_verifier)],
    profiles: Annotated[ProfileRepository, Depends(provide_profile_repository)],
) -> AuthenticateUser:
    return AuthenticateUser(verifier, profiles)


auth = build_auth_dependencies(provide_authenticate_user)


# --- monitoring: zones ----------------------------------------------------------------


def provide_zone_repository(session: SessionDep) -> ZoneRepository:
    return SqlAlchemyZoneRepository(session)


def provide_list_zones(
    zones: Annotated[ZoneRepository, Depends(provide_zone_repository)],
) -> ListZones:
    return ListZones(zones)


def provide_create_zone(
    zones: Annotated[ZoneRepository, Depends(provide_zone_repository)],
) -> CreateZone:
    return CreateZone(zones)


# --- app ------------------------------------------------------------------------------


def create_app() -> FastAPI:
    app = FastAPI(title="Vigía API", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
    )
    register_problem_handlers(app)
    app.include_router(health_router, prefix="/api")
    app.include_router(
        build_zones_router(auth, provide_list_zones, provide_create_zone), prefix="/api"
    )
    return app
