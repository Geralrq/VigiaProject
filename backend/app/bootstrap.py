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

from app.alerts.adapters.inbound.alerts_router import (
    build_alerts_router,
    build_public_alerts_router,
)
from app.alerts.adapters.outbound.persistence.alert_repository import SqlAlchemyAlertRepository
from app.alerts.adapters.outbound.persistence.recipient_finder import SqlAlchemyRecipientFinder
from app.alerts.application.ports.alert_repository import AlertRepository
from app.alerts.application.ports.recipient_finder import RecipientFinder
from app.alerts.application.use_cases.create_alert import CreateAlertOnAnomalyConfirmed
from app.alerts.application.use_cases.get_alert import GetAlert
from app.alerts.application.use_cases.list_alerts import ListAlerts
from app.inspections.adapters.inbound.inspections_router import build_inspections_router
from app.inspections.adapters.outbound.pdf_report import ReportLabPdfGenerator
from app.inspections.adapters.outbound.persistence.inspection_repository import (
    SqlAlchemyInspectionRepository,
    SqlAlchemyTechnicianDirectory,
    SqlMonitoringEvidenceSource,
)
from app.inspections.application.ports.inspection_ports import (
    EvidenceSource,
    InspectionRepository,
    ReportGeneratorPort,
    TechnicianDirectory,
)
from app.inspections.application.use_cases.create_inspection import CreateInspectionOnAlert
from app.inspections.application.use_cases.inspection_pdf import (
    GenerateInspectionPdf,
    GetInspectionPdf,
)
from app.inspections.application.use_cases.workflow import (
    AddInspectionPhoto,
    AssignInspection,
    CloseInspection,
    GetInspection,
    ListInspections,
    SaveInspectionForm,
)
from app.monitoring.adapters.inbound.anomalies_admin_router import build_anomalies_admin_router
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
from app.monitoring.application.use_cases.confirm_anomaly import ConfirmAnomaly
from app.monitoring.application.use_cases.create_zone import CreateZone
from app.monitoring.application.use_cases.ensure_anomaly_images import EnsureAnomalyImages
from app.monitoring.application.use_cases.get_zone_readings import GetZoneReadings
from app.monitoring.application.use_cases.list_anomalies import ListAnomalies
from app.monitoring.application.use_cases.list_hotspots import ListHotspots
from app.monitoring.application.use_cases.list_zones import ListZones
from app.monitoring.application.use_cases.review_anomaly import DiscardAnomaly, StartAnomalyReview
from app.monitoring.application.use_cases.scan_zones import ScanZones
from app.notifications.adapters.inbound.telegram_router import (
    build_telegram_router,
    build_webhook_guard,
)
from app.notifications.adapters.outbound.persistence.chat_link_repository import (
    SqlAlchemyChatLinkRepository,
)
from app.notifications.adapters.outbound.persistence.web_adapter import WebNotificationAdapter
from app.notifications.adapters.outbound.sms_adapter import SimulatedSmsAdapter
from app.notifications.adapters.outbound.telegram_adapter import TelegramAdapter
from app.notifications.application.ports.chat_link_repository import ChatLinkRepository
from app.notifications.application.ports.notification_port import (
    NotificationPort,
    TelegramChatPort,
)
from app.notifications.application.use_cases.notify_alert import NotifyAlertRecipients
from app.notifications.application.use_cases.telegram_linking import (
    HandleTelegramMessage,
    IssueTelegramLinkCode,
    SetTelegramChat,
)
from app.notifications.domain.link_code import LinkCodeSigner
from app.reports.adapters.inbound.reports_router import (
    build_missions_router,
    build_reports_router,
)
from app.reports.adapters.outbound.monitoring_review import MonitoringAnomalyReview
from app.reports.adapters.outbound.persistence.mission_repository import (
    SqlAlchemyCandidateFinder,
    SqlAlchemyMissionRepository,
    SqlAlchemyScoreRepository,
)
from app.reports.adapters.outbound.persistence.report_repository import SqlAlchemyReportRepository
from app.reports.application.ports.mission_ports import (
    AnomalyReviewPort,
    CandidateFinder,
    MissionRepository,
    ScoreRepository,
)
from app.reports.application.ports.report_repository import ReportRepository
from app.reports.application.use_cases.citizen_reports import CreateReport, ListReports
from app.reports.application.use_cases.missions import (
    CreateVerificationMissions,
    GetLeaderboard,
    ListMyMissions,
    MissionConfig,
    RespondToMission,
)
from app.shared.adapters.inbound.admin_users_router import build_admin_users_router
from app.shared.adapters.inbound.health import router as health_router
from app.shared.adapters.inbound.me_router import build_me_router
from app.shared.adapters.inbound.problems import register_problem_handlers
from app.shared.adapters.inbound.security import build_auth_dependencies, build_cron_guard
from app.shared.adapters.inbound.users_router import build_users_router
from app.shared.adapters.outbound.auth.jwks_token_verifier import (
    JwksTokenVerifier,
    build_jwk_client,
)
from app.shared.adapters.outbound.events.in_memory_bus import InMemoryEventBus
from app.shared.adapters.outbound.persistence.engine import build_engine
from app.shared.adapters.outbound.persistence.my_profile_repository import (
    SqlAlchemyMyProfileRepository,
)
from app.shared.adapters.outbound.persistence.profile_repository import (
    SqlAlchemyProfileRepository,
)
from app.shared.adapters.outbound.persistence.user_admin_repository import (
    SqlAlchemyUserAdminRepository,
)
from app.shared.adapters.outbound.persistence.user_directory import SqlAlchemyUserDirectory
from app.shared.adapters.outbound.storage.in_memory_storage import InMemoryStorage
from app.shared.adapters.outbound.storage.supabase_storage import SupabaseStorageAdapter
from app.shared.application.ports.auth import ProfileRepository, TokenVerifier
from app.shared.application.ports.events import EventPublisher
from app.shared.application.ports.profile import MyProfileRepository
from app.shared.application.ports.storage import StoragePort
from app.shared.application.ports.user_admin import UserAdminRepository
from app.shared.application.ports.user_directory import UserDirectory
from app.shared.application.use_cases.authenticate_user import AuthenticateUser
from app.shared.application.use_cases.list_users import ListUsersByRole
from app.shared.application.use_cases.manage_users import ChangeUserRole, ListManagedUsers
from app.shared.application.use_cases.my_profile import GetMyProfile, UpdateMyProfile
from app.shared.domain.events import AlertCreated, AnomalyConfirmed, AnomalyDetected
from app.shared.settings import get_settings

CORS_ORIGINS = ["http://localhost:3000"]
JWT_AUDIENCE = "authenticated"
EVIDENCE_BUCKET = "evidencias"  # private Supabase Storage bucket (see migration 003)


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


# --- shared: own profile --------------------------------------------------------------


def provide_my_profile_repository(session: SessionDep) -> MyProfileRepository:
    return SqlAlchemyMyProfileRepository(session)


def provide_get_my_profile(
    profiles: Annotated[MyProfileRepository, Depends(provide_my_profile_repository)],
) -> GetMyProfile:
    return GetMyProfile(profiles)


def provide_update_my_profile(
    profiles: Annotated[MyProfileRepository, Depends(provide_my_profile_repository)],
) -> UpdateMyProfile:
    return UpdateMyProfile(profiles)


# --- shared: user directory (id and name only) ------------------------------------------


def provide_user_directory(session: SessionDep) -> UserDirectory:
    return SqlAlchemyUserDirectory(session)


def provide_list_users(
    users: Annotated[UserDirectory, Depends(provide_user_directory)],
) -> ListUsersByRole:
    return ListUsersByRole(users)


# --- shared: user management (ADMIN) ---------------------------------------------------


def provide_user_admin_repository(session: SessionDep) -> UserAdminRepository:
    return SqlAlchemyUserAdminRepository(session)


def provide_list_managed_users(
    users: Annotated[UserAdminRepository, Depends(provide_user_admin_repository)],
) -> ListManagedUsers:
    return ListManagedUsers(users)


def provide_change_user_role(
    users: Annotated[UserAdminRepository, Depends(provide_user_admin_repository)],
) -> ChangeUserRole:
    return ChangeUserRole(users)


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


def provide_get_zone_readings(
    zones: Annotated[ZoneRepository, Depends(provide_zone_repository)],
    readings: Annotated[IndexReadingRepository, Depends(provide_index_reading_repository)],
) -> GetZoneReadings:
    return GetZoneReadings(zones, readings)


def provide_fire_hotspot_repository(session: SessionDep) -> FireHotspotRepository:
    return SqlAlchemyFireHotspotRepository(session)


def provide_anomaly_repository(session: SessionDep) -> AnomalyRepository:
    return SqlAlchemyAnomalyRepository(session)


def provide_carbon_factor_repository(session: SessionDep) -> CarbonFactorRepository:
    return SqlAlchemyCarbonFactorRepository(session)


# --- shared: event bus, alerts and notifications ----------------------------------------


def provide_critical_confidence() -> float:
    return get_settings().critical_confidence_threshold


# provide_event_bus -> (alerts, notifiers) -> provide_event_publisher: the handlers need the
# bus to publish follow-up events, so the subscriptions are wired in a second step.


def provide_event_bus() -> InMemoryEventBus:
    """One bus per request (FastAPI caches the dependency within a request)."""
    return InMemoryEventBus()


def provide_alert_repository(session: SessionDep) -> AlertRepository:
    return SqlAlchemyAlertRepository(session)


def provide_recipient_finder(session: SessionDep) -> RecipientFinder:
    return SqlAlchemyRecipientFinder(session)


@lru_cache  # singleton: one HTTP client for the Telegram API
def provide_telegram_adapter() -> TelegramAdapter:
    settings = get_settings()
    return TelegramAdapter(settings.telegram_bot_token.get_secret_value(), settings.public_app_url)


def provide_telegram_chat() -> TelegramChatPort:
    return provide_telegram_adapter()


def provide_notifiers(session: SessionDep) -> list[NotificationPort]:
    public_url = get_settings().public_app_url
    return [
        WebNotificationAdapter(session, public_url),
        provide_telegram_adapter(),
        SimulatedSmsAdapter(public_url),
    ]


def provide_create_alert(
    bus: Annotated[InMemoryEventBus, Depends(provide_event_bus)],
    alerts: Annotated[AlertRepository, Depends(provide_alert_repository)],
    recipients: Annotated[RecipientFinder, Depends(provide_recipient_finder)],
) -> CreateAlertOnAnomalyConfirmed:
    return CreateAlertOnAnomalyConfirmed(alerts, recipients, bus)


def provide_notify_alert(
    notifiers: Annotated[list[NotificationPort], Depends(provide_notifiers)],
) -> NotifyAlertRecipients:
    return NotifyAlertRecipients(notifiers)


def provide_list_alerts(
    alerts: Annotated[AlertRepository, Depends(provide_alert_repository)],
) -> ListAlerts:
    return ListAlerts(alerts)


def provide_get_alert(
    alerts: Annotated[AlertRepository, Depends(provide_alert_repository)],
) -> GetAlert:
    return GetAlert(alerts)


def provide_chat_link_repository(session: SessionDep) -> ChatLinkRepository:
    return SqlAlchemyChatLinkRepository(session)


def provide_link_code_signer() -> LinkCodeSigner:
    return LinkCodeSigner(get_settings().telegram_link_secret.get_secret_value())


def provide_issue_link_code(
    signer: Annotated[LinkCodeSigner, Depends(provide_link_code_signer)],
) -> IssueTelegramLinkCode:
    return IssueTelegramLinkCode(signer)


def provide_set_telegram_chat(
    links: Annotated[ChatLinkRepository, Depends(provide_chat_link_repository)],
) -> SetTelegramChat:
    # A hand-typed chat id could point alerts at someone else's chat: demo/test only.
    return SetTelegramChat(links, allow_manual=get_settings().app_mode != "live")


def provide_handle_telegram_message(
    signer: Annotated[LinkCodeSigner, Depends(provide_link_code_signer)],
    links: Annotated[ChatLinkRepository, Depends(provide_chat_link_repository)],
    chat: Annotated[TelegramChatPort, Depends(provide_telegram_chat)],
) -> HandleTelegramMessage:
    return HandleTelegramMessage(signer, links, chat)


def provide_telegram_bot_username() -> str:
    return get_settings().telegram_bot_username


def provide_telegram_webhook_secret() -> str:
    return get_settings().telegram_webhook_secret.get_secret_value()


telegram_webhook_guard = build_webhook_guard(provide_telegram_webhook_secret)


# --- reports: storage, citizen reports, verification missions ---------------------------


@lru_cache  # singleton: one HTTP client for Supabase Storage
def provide_storage() -> StoragePort:
    settings = get_settings()
    key = settings.supabase_service_key.get_secret_value()
    if key and settings.supabase_url:
        return SupabaseStorageAdapter(settings.supabase_url, key, EVIDENCE_BUCKET)
    if settings.app_mode == "demo":
        return InMemoryStorage(EVIDENCE_BUCKET)  # marker URLs, nothing leaves the process
    # live without a key: fails with 503 only when a file is actually involved
    return SupabaseStorageAdapter(settings.supabase_url, "", EVIDENCE_BUCKET)


def provide_mission_config() -> MissionConfig:
    settings = get_settings()
    return MissionConfig(
        radius_m=settings.mission_radius_m,
        base_points=settings.mission_base_points,
        bonus_points=settings.mission_bonus_points,
    )


def provide_report_repository(session: SessionDep) -> ReportRepository:
    return SqlAlchemyReportRepository(session)


def provide_mission_repository(session: SessionDep) -> MissionRepository:
    return SqlAlchemyMissionRepository(session)


def provide_candidate_finder(session: SessionDep) -> CandidateFinder:
    return SqlAlchemyCandidateFinder(session)


def provide_score_repository(session: SessionDep) -> ScoreRepository:
    return SqlAlchemyScoreRepository(session)


def provide_anomaly_review(
    anomalies: Annotated[AnomalyRepository, Depends(provide_anomaly_repository)],
    zones: Annotated[ZoneRepository, Depends(provide_zone_repository)],
    bus: Annotated[InMemoryEventBus, Depends(provide_event_bus)],
) -> AnomalyReviewPort:
    # The raw bus (not provide_event_publisher): the publisher itself needs this adapter.
    return MonitoringAnomalyReview(
        anomalies,
        StartAnomalyReview(anomalies),
        ConfirmAnomaly(anomalies, zones, bus),
        DiscardAnomaly(anomalies, zones),
    )


def provide_create_missions(
    missions: Annotated[MissionRepository, Depends(provide_mission_repository)],
    candidates: Annotated[CandidateFinder, Depends(provide_candidate_finder)],
    review: Annotated[AnomalyReviewPort, Depends(provide_anomaly_review)],
    notifiers: Annotated[list[NotificationPort], Depends(provide_notifiers)],
    config: Annotated[MissionConfig, Depends(provide_mission_config)],
) -> CreateVerificationMissions:
    return CreateVerificationMissions(missions, candidates, review, notifiers, config)


def provide_list_my_missions(
    missions: Annotated[MissionRepository, Depends(provide_mission_repository)],
    storage: Annotated[StoragePort, Depends(provide_storage)],
) -> ListMyMissions:
    return ListMyMissions(missions, storage)


def provide_leaderboard(
    scores: Annotated[ScoreRepository, Depends(provide_score_repository)],
) -> GetLeaderboard:
    return GetLeaderboard(scores)


def provide_create_report(
    reports: Annotated[ReportRepository, Depends(provide_report_repository)],
    storage: Annotated[StoragePort, Depends(provide_storage)],
) -> CreateReport:
    return CreateReport(reports, storage)


def provide_list_reports(
    reports: Annotated[ReportRepository, Depends(provide_report_repository)],
    storage: Annotated[StoragePort, Depends(provide_storage)],
) -> ListReports:
    return ListReports(reports, storage)


# --- inspections: tickets ---------------------------------------------------------------


def provide_inspection_repository(session: SessionDep) -> InspectionRepository:
    return SqlAlchemyInspectionRepository(session)


def provide_create_inspection(
    inspections: Annotated[InspectionRepository, Depends(provide_inspection_repository)],
) -> CreateInspectionOnAlert:
    return CreateInspectionOnAlert(inspections)


# --- event publisher: wires every subscriber (needs the blocks above) ---------------------


def provide_event_publisher(
    bus: Annotated[InMemoryEventBus, Depends(provide_event_bus)],
    create_alert: Annotated[CreateAlertOnAnomalyConfirmed, Depends(provide_create_alert)],
    notify_alert: Annotated[NotifyAlertRecipients, Depends(provide_notify_alert)],
    create_missions: Annotated[CreateVerificationMissions, Depends(provide_create_missions)],
    create_inspection: Annotated[CreateInspectionOnAlert, Depends(provide_create_inspection)],
) -> EventPublisher:
    bus.subscribe(AnomalyConfirmed, create_alert.handle)
    bus.subscribe(AlertCreated, notify_alert.handle)
    bus.subscribe(AnomalyDetected, create_missions.handle)
    bus.subscribe(AlertCreated, create_inspection.handle)
    return bus


def provide_respond_to_mission(
    missions: Annotated[MissionRepository, Depends(provide_mission_repository)],
    scores: Annotated[ScoreRepository, Depends(provide_score_repository)],
    review: Annotated[AnomalyReviewPort, Depends(provide_anomaly_review)],
    storage: Annotated[StoragePort, Depends(provide_storage)],
    config: Annotated[MissionConfig, Depends(provide_mission_config)],
    _wired: Annotated[EventPublisher, Depends(provide_event_publisher)],
) -> RespondToMission:
    # `_wired` only guarantees the bus has its subscribers: confirming an anomaly from here
    # publishes AnomalyConfirmed, which must reach the alerts module.
    return RespondToMission(missions, scores, review, storage, config)


def provide_ensure_anomaly_images(
    anomalies: Annotated[AnomalyRepository, Depends(provide_anomaly_repository)],
    satellite: Annotated[SatelliteIndexPort, Depends(provide_satellite_index)],
    storage: Annotated[StoragePort, Depends(provide_storage)],
) -> EnsureAnomalyImages:
    return EnsureAnomalyImages(anomalies, satellite, storage)


# --- inspections: workflow and PDF report ----------------------------------------------


def provide_public_app_url() -> str:
    return get_settings().public_app_url


def provide_technician_directory(session: SessionDep) -> TechnicianDirectory:
    return SqlAlchemyTechnicianDirectory(session)


def provide_evidence_source(
    session: SessionDep,
    ensure_images: Annotated[EnsureAnomalyImages, Depends(provide_ensure_anomaly_images)],
    readings: Annotated[IndexReadingRepository, Depends(provide_index_reading_repository)],
) -> EvidenceSource:
    return SqlMonitoringEvidenceSource(session, ensure_images, readings)


@lru_cache
def provide_report_generator() -> ReportGeneratorPort:
    return ReportLabPdfGenerator()


def provide_generate_pdf(
    inspections: Annotated[InspectionRepository, Depends(provide_inspection_repository)],
    evidence: Annotated[EvidenceSource, Depends(provide_evidence_source)],
    storage: Annotated[StoragePort, Depends(provide_storage)],
    generator: Annotated[ReportGeneratorPort, Depends(provide_report_generator)],
    public_url: Annotated[str, Depends(provide_public_app_url)],
) -> GenerateInspectionPdf:
    return GenerateInspectionPdf(inspections, evidence, storage, generator, public_url)


def provide_get_inspection_pdf(
    inspections: Annotated[InspectionRepository, Depends(provide_inspection_repository)],
    pdf: Annotated[GenerateInspectionPdf, Depends(provide_generate_pdf)],
) -> GetInspectionPdf:
    return GetInspectionPdf(inspections, pdf)


def provide_list_inspections(
    inspections: Annotated[InspectionRepository, Depends(provide_inspection_repository)],
    storage: Annotated[StoragePort, Depends(provide_storage)],
) -> ListInspections:
    return ListInspections(inspections, storage)


def provide_get_inspection(
    inspections: Annotated[InspectionRepository, Depends(provide_inspection_repository)],
    storage: Annotated[StoragePort, Depends(provide_storage)],
) -> GetInspection:
    return GetInspection(inspections, storage)


def provide_assign_inspection(
    inspections: Annotated[InspectionRepository, Depends(provide_inspection_repository)],
    technicians: Annotated[TechnicianDirectory, Depends(provide_technician_directory)],
    notifiers: Annotated[list[NotificationPort], Depends(provide_notifiers)],
    storage: Annotated[StoragePort, Depends(provide_storage)],
) -> AssignInspection:
    return AssignInspection(inspections, technicians, notifiers, storage)


def provide_add_inspection_photo(
    inspections: Annotated[InspectionRepository, Depends(provide_inspection_repository)],
    storage: Annotated[StoragePort, Depends(provide_storage)],
) -> AddInspectionPhoto:
    return AddInspectionPhoto(inspections, storage)


def provide_save_inspection_form(
    inspections: Annotated[InspectionRepository, Depends(provide_inspection_repository)],
    storage: Annotated[StoragePort, Depends(provide_storage)],
) -> SaveInspectionForm:
    return SaveInspectionForm(inspections, storage)


def provide_close_inspection(
    inspections: Annotated[InspectionRepository, Depends(provide_inspection_repository)],
    pdf: Annotated[GenerateInspectionPdf, Depends(provide_generate_pdf)],
    storage: Annotated[StoragePort, Depends(provide_storage)],
) -> CloseInspection:
    return CloseInspection(inspections, pdf, storage)


# --- monitoring: scan and confirm (publish events) ------------------------------------


def provide_scan_zones(
    zones: Annotated[ZoneRepository, Depends(provide_zone_repository)],
    satellite: Annotated[SatelliteIndexPort, Depends(provide_satellite_index)],
    fire_source: Annotated[FireHotspotPort, Depends(provide_fire_hotspot_source)],
    readings: Annotated[IndexReadingRepository, Depends(provide_index_reading_repository)],
    hotspots: Annotated[FireHotspotRepository, Depends(provide_fire_hotspot_repository)],
    anomalies: Annotated[AnomalyRepository, Depends(provide_anomaly_repository)],
    carbon: Annotated[CarbonFactorRepository, Depends(provide_carbon_factor_repository)],
    events: Annotated[EventPublisher, Depends(provide_event_publisher)],
    critical_confidence: Annotated[float, Depends(provide_critical_confidence)],
) -> ScanZones:
    return ScanZones(
        zones,
        satellite,
        fire_source,
        readings,
        hotspots,
        anomalies,
        carbon,
        events=events,
        critical_confidence=critical_confidence,
    )


def provide_confirm_anomaly(
    anomalies: Annotated[AnomalyRepository, Depends(provide_anomaly_repository)],
    zones: Annotated[ZoneRepository, Depends(provide_zone_repository)],
    events: Annotated[EventPublisher, Depends(provide_event_publisher)],
) -> ConfirmAnomaly:
    return ConfirmAnomaly(anomalies, zones, events)


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
        build_me_router(auth, provide_get_my_profile, provide_update_my_profile), prefix="/api"
    )
    app.include_router(build_users_router(auth, provide_list_users), prefix="/api")
    app.include_router(
        build_admin_users_router(auth, provide_list_managed_users, provide_change_user_role),
        prefix="/api",
    )
    app.include_router(
        build_zones_router(
            auth, provide_list_zones, provide_create_zone, provide_get_zone_readings
        ),
        prefix="/api",
    )
    app.include_router(build_scan_router(auth, cron_guard, provide_scan_zones), prefix="/api")
    app.include_router(
        build_anomalies_router(auth, provide_list_anomalies, provide_ensure_anomaly_images),
        prefix="/api",
    )
    app.include_router(build_hotspots_router(auth, provide_list_hotspots), prefix="/api")
    app.include_router(build_anomalies_admin_router(auth, provide_confirm_anomaly), prefix="/api")
    app.include_router(
        build_alerts_router(auth, provide_list_alerts, provide_get_alert), prefix="/api"
    )
    app.include_router(build_public_alerts_router(provide_get_alert), prefix="/api")
    app.include_router(
        build_inspections_router(
            auth,
            provide_list_inspections,
            provide_get_inspection,
            provide_assign_inspection,
            provide_add_inspection_photo,
            provide_save_inspection_form,
            provide_close_inspection,
            provide_get_inspection_pdf,
        ),
        prefix="/api",
    )
    app.include_router(
        build_reports_router(auth, provide_create_report, provide_list_reports), prefix="/api"
    )
    app.include_router(
        build_missions_router(
            auth, provide_list_my_missions, provide_respond_to_mission, provide_leaderboard
        ),
        prefix="/api",
    )
    app.include_router(
        build_telegram_router(
            auth,
            telegram_webhook_guard,
            provide_issue_link_code,
            provide_set_telegram_chat,
            provide_handle_telegram_message,
            provide_telegram_bot_username,
        ),
        prefix="/api",
    )
    return app
