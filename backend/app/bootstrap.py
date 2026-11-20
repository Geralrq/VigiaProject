"""Composition root: the only module that knows concrete adapters.

Each `provide_*` function is a FastAPI dependency. Routers receive providers as
arguments, so tests swap any of them via `app.dependency_overrides[provide_x]`.
"""

import logging
from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.monitoring.adapters.inbound.anomalies_router import build_anomalies_router
from app.monitoring.adapters.inbound.hotspots_router import build_hotspots_router
from app.monitoring.adapters.inbound.scan_router import build_scan_router
from app.monitoring.adapters.inbound.zones_router import build_zones_router
from app.monitoring.adapters.outbound.fires.demo_fire_adapter import DemoFireHotspotAdapter
from app.monitoring.adapters.outbound.fires.firms_adapter import FirmsAreaAdapter
from app.monitoring.adapters.outbound.persistence.anomaly_repository import (
    SqlAlchemyAnomalyRepository,
)
from app.monitoring.adapters.outbound.persistence.carbon_factor_repository import (
    SqlAlchemyCarbonFactorRepository,
)
from app.monitoring.adapters.outbound.persistence.fire_hotspot_repository import (
    SqlAlchemyFireHotspotRepository,
)
from app.monitoring.adapters.outbound.persistence.index_reading_repository import (
    SqlAlchemyIndexReadingRepository,
)
from app.monitoring.adapters.outbound.persistence.zone_repository import SqlAlchemyZoneRepository
from app.monitoring.adapters.outbound.satellite.demo_satellite_adapter import (
    DemoSatelliteIndexAdapter,
)
from app.monitoring.adapters.outbound.satellite.sentinel_hub_adapter import (
    SentinelHubStatisticalAdapter,
)
from app.monitoring.application.ports.anomaly_repository import AnomalyRepository
from app.monitoring.application.ports.carbon_factor_repository import CarbonFactorRepository
from app.monitoring.application.ports.fire_hotspot_port import FireHotspotPort
from app.monitoring.application.ports.fire_hotspot_repository import FireHotspotRepository
from app.monitoring.application.ports.index_reading_repository import IndexReadingRepository
from app.monitoring.application.ports.satellite_index_port import SatelliteIndexPort
from app.monitoring.application.ports.zone_repository import ZoneRepository
from app.monitoring.application.use_cases.create_zone import CreateZone
from app.monitoring.application.use_cases.list_anomalies import ListAnomalies
from app.monitoring.application.use_cases.list_hotspots import ListHotspots
from app.monitoring.application.use_cases.list_zones import ListZones
from app.monitoring.application.use_cases.scan_zones import ScanZones
from app.shared.adapters.inbound.health import router as health_router
from app.shared.adapters.inbound.problems import register_problem_handlers
from app.shared.adapters.inbound.security import build_auth_dependencies, build_cron_guard
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


# --- monitoring: satellite engine -----------------------------------------------------


def provide_cron_secret() -> str:
    return get_settings().cron_secret.get_secret_value()


cron_guard = build_cron_guard(provide_cron_secret)


@lru_cache  # singleton: keeps the Copernicus OAuth token cached until it expires
def provide_satellite_index() -> SatelliteIndexPort:
    settings = get_settings()
    if settings.app_mode == "live":
        return SentinelHubStatisticalAdapter(
            settings.sentinel_client_id.get_secret_value(),
            settings.sentinel_client_secret.get_secret_value(),
        )
    return DemoSatelliteIndexAdapter()


@lru_cache
def provide_fire_hotspot_source() -> FireHotspotPort:
    settings = get_settings()
    if settings.app_mode == "live":
        return FirmsAreaAdapter(settings.firms_map_key.get_secret_value())
    return DemoFireHotspotAdapter()


def provide_index_reading_repository(session: SessionDep) -> IndexReadingRepository:
    return SqlAlchemyIndexReadingRepository(session)


def provide_fire_hotspot_repository(session: SessionDep) -> FireHotspotRepository:
    return SqlAlchemyFireHotspotRepository(session)


def provide_anomaly_repository(session: SessionDep) -> AnomalyRepository:
    return SqlAlchemyAnomalyRepository(session)


def provide_carbon_factor_repository(session: SessionDep) -> CarbonFactorRepository:
    return SqlAlchemyCarbonFactorRepository(session)


def provide_scan_zones(
    zones: Annotated[ZoneRepository, Depends(provide_zone_repository)],
    satellite: Annotated[SatelliteIndexPort, Depends(provide_satellite_index)],
    fire_source: Annotated[FireHotspotPort, Depends(provide_fire_hotspot_source)],
    readings: Annotated[IndexReadingRepository, Depends(provide_index_reading_repository)],
    hotspots: Annotated[FireHotspotRepository, Depends(provide_fire_hotspot_repository)],
    anomalies: Annotated[AnomalyRepository, Depends(provide_anomaly_repository)],
    carbon: Annotated[CarbonFactorRepository, Depends(provide_carbon_factor_repository)],
) -> ScanZones:
    return ScanZones(zones, satellite, fire_source, readings, hotspots, anomalies, carbon)


def provide_list_anomalies(
    anomalies: Annotated[AnomalyRepository, Depends(provide_anomaly_repository)],
) -> ListAnomalies:
    return ListAnomalies(anomalies)


def provide_list_hotspots(
    hotspots: Annotated[FireHotspotRepository, Depends(provide_fire_hotspot_repository)],
) -> ListHotspots:
    return ListHotspots(hotspots)


# --- app ------------------------------------------------------------------------------


def create_app() -> FastAPI:
    # httpx logs full URLs at INFO; the FIRMS URL carries the map key.
    logging.getLogger("httpx").setLevel(logging.WARNING)
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
    app.include_router(build_scan_router(auth, cron_guard, provide_scan_zones), prefix="/api")
    app.include_router(build_anomalies_router(auth, provide_list_anomalies), prefix="/api")
    app.include_router(build_hotspots_router(auth, provide_list_hotspots), prefix="/api")
    return app
