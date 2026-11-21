import logging
import time
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from jwt import PyJWKClient
from jwt.algorithms import ECAlgorithm

from app.bootstrap import (
    create_app,
    provide_alert_repository,
    provide_anomaly_repository,
    provide_candidate_finder,
    provide_carbon_factor_repository,
    provide_chat_link_repository,
    provide_critical_confidence,
    provide_cron_secret,
    provide_evidence_source,
    provide_fire_hotspot_repository,
    provide_fire_hotspot_source,
    provide_index_reading_repository,
    provide_inspection_repository,
    provide_link_code_signer,
    provide_mission_config,
    provide_mission_repository,
    provide_my_profile_repository,
    provide_notifiers,
    provide_profile_repository,
    provide_public_app_url,
    provide_recipient_finder,
    provide_report_generator,
    provide_report_repository,
    provide_satellite_index,
    provide_score_repository,
    provide_session,
    provide_set_telegram_chat,
    provide_storage,
    provide_technician_directory,
    provide_telegram_bot_username,
    provide_telegram_chat,
    provide_telegram_webhook_secret,
    provide_token_verifier,
    provide_user_directory,
    provide_zone_repository,
)
from app.monitoring.adapters.outbound.fires.demo_fire_adapter import DemoFireHotspotAdapter
from app.monitoring.adapters.outbound.satellite.demo_satellite_adapter import (
    DemoSatelliteIndexAdapter,
)
from app.notifications.application.use_cases.telegram_linking import SetTelegramChat
from app.notifications.domain.link_code import LinkCodeSigner
from app.notifications.domain.notice import Channel
from app.reports.application.use_cases.missions import MissionConfig
from app.shared.adapters.outbound.auth.jwks_token_verifier import JwksTokenVerifier
from app.shared.adapters.outbound.storage.in_memory_storage import InMemoryStorage
from tests.fakes import (
    InMemoryAnomalyRepository,
    InMemoryCarbonFactorRepository,
    InMemoryFireHotspotRepository,
    InMemoryIndexReadingRepository,
    InMemoryProfileRepository,
    InMemoryZoneRepository,
)
from tests.fakes_alerts import (
    FakeRecipientFinder,
    FakeTelegramChat,
    InMemoryAlertRepository,
    InMemoryChatLinkRepository,
    RecordingNotifier,
)
from tests.fakes_inspections import (
    FakeEvidenceSource,
    FakePdfGenerator,
    InMemoryInspectionRepository,
    InMemoryTechnicianDirectory,
)
from tests.fakes_profile import InMemoryMyProfileRepository, InMemoryUserDirectory
from tests.fakes_reports import (
    FakeCandidateFinder,
    InMemoryMissionRepository,
    InMemoryReportRepository,
    InMemoryScoreRepository,
)

ISSUER = "https://test-project.supabase.co/auth/v1"
AUDIENCE = "authenticated"
KID = "test-key-1"
CRON_SECRET = "test-cron-secret-0123456789"
WEBHOOK_SECRET = "test-webhook-secret-0123456789"
LINK_SECRET = "test-link-secret-0123456789"
BOT_USERNAME = "VigiaTestBot"
PUBLIC_URL = "https://vigia.example"

TokenFactory = Callable[..., str]


class StaticJWKClient(PyJWKClient):
    """Real PyJWKClient (kid lookup, PyJWK parsing) whose fetch never hits the network."""

    def __init__(self, jwks: dict[str, Any]) -> None:
        super().__init__("https://jwks.invalid/.well-known/jwks.json", cache_keys=True)
        self._jwks = jwks

    def fetch_data(self) -> Any:
        return self._jwks


def _no_database():
    raise RuntimeError("tests must not touch the database: override this provider")


@pytest.fixture(autouse=True)
def _enable_app_loggers() -> None:
    """import-linter (test_architecture) configures logging and disables existing loggers."""
    for name, logger in list(logging.root.manager.loggerDict.items()):
        if name.startswith("app") and isinstance(logger, logging.Logger):
            logger.disabled = False


@pytest.fixture(scope="session")
def private_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture(scope="session")
def jwks(private_key: ec.EllipticCurvePrivateKey) -> dict[str, Any]:
    jwk = ECAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    jwk.update(kid=KID, alg="ES256", use="sig")
    return {"keys": [jwk]}


@pytest.fixture
def verifier(jwks: dict[str, Any]) -> JwksTokenVerifier:
    return JwksTokenVerifier(StaticJWKClient(jwks), audience=AUDIENCE, issuer=ISSUER)


@pytest.fixture
def make_token(private_key: ec.EllipticCurvePrivateKey) -> TokenFactory:
    def factory(
        sub: UUID | str | None = None,
        *,
        expires_in: int = 3600,
        key: ec.EllipticCurvePrivateKey | None = None,
        kid: str = KID,
        **overrides: Any,
    ) -> str:
        now = int(time.time())
        claims: dict[str, Any] = {
            "sub": str(sub or uuid4()),
            "aud": AUDIENCE,
            "iss": ISSUER,
            "iat": now,
            "exp": now + expires_in,
            "email": "ana@example.org",
            "role": "authenticated",
            "user_metadata": {"full_name": "Ana Pérez"},
        }
        claims.update(overrides)
        return jwt.encode(claims, key or private_key, algorithm="ES256", headers={"kid": kid})

    return factory


@pytest.fixture
def profiles() -> InMemoryProfileRepository:
    return InMemoryProfileRepository()


@pytest.fixture
def zones() -> InMemoryZoneRepository:
    return InMemoryZoneRepository()


@pytest.fixture
def readings() -> InMemoryIndexReadingRepository:
    return InMemoryIndexReadingRepository()


@pytest.fixture
def anomalies() -> InMemoryAnomalyRepository:
    return InMemoryAnomalyRepository()


@pytest.fixture
def hotspots() -> InMemoryFireHotspotRepository:
    return InMemoryFireHotspotRepository()


@pytest.fixture
def alerts(
    anomalies: InMemoryAnomalyRepository, zones: InMemoryZoneRepository
) -> InMemoryAlertRepository:
    return InMemoryAlertRepository(anomalies, zones)


@pytest.fixture
def recipients() -> FakeRecipientFinder:
    return FakeRecipientFinder()


@pytest.fixture
def web_notifier() -> RecordingNotifier:
    return RecordingNotifier(Channel.WEB)


@pytest.fixture
def telegram_notifier() -> RecordingNotifier:
    return RecordingNotifier(Channel.TELEGRAM)


@pytest.fixture
def telegram_chat() -> FakeTelegramChat:
    return FakeTelegramChat()


@pytest.fixture
def chat_links() -> InMemoryChatLinkRepository:
    return InMemoryChatLinkRepository()


@pytest.fixture
def my_profiles(profiles: InMemoryProfileRepository) -> InMemoryMyProfileRepository:
    return InMemoryMyProfileRepository(profiles)


@pytest.fixture
def users(profiles: InMemoryProfileRepository) -> InMemoryUserDirectory:
    return InMemoryUserDirectory(profiles)


@pytest.fixture
def inspections(
    alerts: InMemoryAlertRepository,
    anomalies: InMemoryAnomalyRepository,
    zones: InMemoryZoneRepository,
    profiles: InMemoryProfileRepository,
) -> InMemoryInspectionRepository:
    return InMemoryInspectionRepository(alerts, anomalies, zones, profiles)


@pytest.fixture
def technicians(profiles: InMemoryProfileRepository) -> InMemoryTechnicianDirectory:
    return InMemoryTechnicianDirectory(profiles)


@pytest.fixture
def evidence() -> FakeEvidenceSource:
    return FakeEvidenceSource()


@pytest.fixture
def pdf_generator() -> FakePdfGenerator:
    return FakePdfGenerator()


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def reports() -> InMemoryReportRepository:
    return InMemoryReportRepository()


@pytest.fixture
def missions(
    anomalies: InMemoryAnomalyRepository, zones: InMemoryZoneRepository
) -> InMemoryMissionRepository:
    return InMemoryMissionRepository(anomalies, zones)


@pytest.fixture
def candidates() -> FakeCandidateFinder:
    return FakeCandidateFinder()


@pytest.fixture
def scores() -> InMemoryScoreRepository:
    return InMemoryScoreRepository()


@pytest.fixture
def link_signer() -> LinkCodeSigner:
    return LinkCodeSigner(LINK_SECRET)


@pytest.fixture
def client(
    verifier: JwksTokenVerifier,
    profiles: InMemoryProfileRepository,
    zones: InMemoryZoneRepository,
    readings: InMemoryIndexReadingRepository,
    anomalies: InMemoryAnomalyRepository,
    hotspots: InMemoryFireHotspotRepository,
    alerts: InMemoryAlertRepository,
    recipients: FakeRecipientFinder,
    web_notifier: RecordingNotifier,
    telegram_notifier: RecordingNotifier,
    telegram_chat: FakeTelegramChat,
    chat_links: InMemoryChatLinkRepository,
    link_signer: LinkCodeSigner,
    storage: InMemoryStorage,
    reports: InMemoryReportRepository,
    missions: InMemoryMissionRepository,
    candidates: FakeCandidateFinder,
    scores: InMemoryScoreRepository,
    my_profiles: InMemoryMyProfileRepository,
    users: InMemoryUserDirectory,
    inspections: InMemoryInspectionRepository,
    technicians: InMemoryTechnicianDirectory,
    evidence: FakeEvidenceSource,
    pdf_generator: FakePdfGenerator,
) -> TestClient:
    """App wired to in-memory repos and the demo (offline) satellite/FIRMS adapters."""
    carbon = InMemoryCarbonFactorRepository({"bosque_amazonico": 180.0})
    app = create_app()
    overrides = {
        provide_token_verifier: lambda: verifier,
        provide_profile_repository: lambda: profiles,
        provide_zone_repository: lambda: zones,
        provide_anomaly_repository: lambda: anomalies,
        provide_fire_hotspot_repository: lambda: hotspots,
        provide_index_reading_repository: lambda: readings,
        provide_carbon_factor_repository: lambda: carbon,
        provide_satellite_index: lambda: DemoSatelliteIndexAdapter(),
        provide_fire_hotspot_source: lambda: DemoFireHotspotAdapter(),
        provide_cron_secret: lambda: CRON_SECRET,
        provide_alert_repository: lambda: alerts,
        provide_recipient_finder: lambda: recipients,
        provide_notifiers: lambda: [web_notifier, telegram_notifier],
        provide_telegram_chat: lambda: telegram_chat,
        provide_chat_link_repository: lambda: chat_links,
        provide_link_code_signer: lambda: link_signer,
        provide_telegram_webhook_secret: lambda: WEBHOOK_SECRET,
        provide_telegram_bot_username: lambda: BOT_USERNAME,
        provide_critical_confidence: lambda: 0.75,
        provide_storage: lambda: storage,
        provide_my_profile_repository: lambda: my_profiles,
        provide_user_directory: lambda: users,
        provide_inspection_repository: lambda: inspections,
        provide_technician_directory: lambda: technicians,
        provide_evidence_source: lambda: evidence,
        provide_report_generator: lambda: pdf_generator,
        provide_public_app_url: lambda: PUBLIC_URL,
        provide_report_repository: lambda: reports,
        provide_mission_repository: lambda: missions,
        provide_candidate_finder: lambda: candidates,
        provide_score_repository: lambda: scores,
        provide_mission_config: lambda: MissionConfig(),
        provide_session: _no_database,  # any provider left un-overridden fails loudly
        provide_set_telegram_chat: lambda: SetTelegramChat(chat_links, allow_manual=True),
    }
    app.dependency_overrides.update(overrides)
    return TestClient(app)
