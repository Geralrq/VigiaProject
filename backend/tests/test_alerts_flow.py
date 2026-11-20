"""Reaction to AnomalyConfirmed: recipients, idempotency, channel tolerance, the event bus."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.alerts.application.use_cases.create_alert import (
    CreateAlertOnAnomalyConfirmed,
    select_recipients,
)
from app.alerts.domain.alert import alert_id
from app.alerts.domain.risk import RiskLevel
from app.monitoring.application.use_cases.confirm_anomaly import ConfirmAnomaly
from app.monitoring.domain.anomaly import Anomaly, AnomalyState, AnomalyType
from app.monitoring.domain.impact import ImpactEstimate
from app.monitoring.domain.zone import Zone
from app.notifications.application.use_cases.notify_alert import NotifyAlertRecipients
from app.notifications.domain.notice import AlertNotice, Channel, compose_text
from app.shared.adapters.outbound.events.in_memory_bus import InMemoryEventBus
from app.shared.domain.errors import DomainValidationError, NotFoundError
from app.shared.domain.events import AlertCreated, AnomalyConfirmed, Recipient
from tests.fakes import InMemoryAnomalyRepository, InMemoryZoneRepository
from tests.fakes_alerts import (
    FakeRecipientFinder,
    InMemoryAlertRepository,
    RecordingNotifier,
    RecordingPublisher,
)
from tests.test_zones_use_cases import square

NOW = datetime(2026, 11, 19, 12, tzinfo=UTC)
AREA = square(-72.8, 1.85, 0.3)  # fence reaches 20 km past this when CRITICO


def confirmed_event(**overrides: object) -> AnomalyConfirmed:
    data: dict[str, object] = {
        "anomaly_id": uuid4(),
        "zone_id": uuid4(),
        "zone_name": "Guaviare",
        "anomaly_type": "DEFORESTACION",
        "confidence": 0.87,
        "hectares": 120.0,
        "co2_tonnes": 79_200.0,
        "geometry": AREA,
        "detected_at": NOW,
    }
    return AnomalyConfirmed(**(data | overrides))  # type: ignore[arg-type]


class Setup:
    def __init__(self) -> None:
        self.anomalies = InMemoryAnomalyRepository()
        self.zones = InMemoryZoneRepository()
        self.alerts = InMemoryAlertRepository(self.anomalies, self.zones)
        self.finder = FakeRecipientFinder()
        self.published = RecordingPublisher()
        self.handler = CreateAlertOnAnomalyConfirmed(
            self.alerts, self.finder, self.published, clock=lambda: NOW
        )

    @property
    def created(self) -> list[AlertCreated]:
        return [e for e in self.published.events if isinstance(e, AlertCreated)]


@pytest.fixture
def setup() -> Setup:
    return Setup()


# --- recipient selection ----------------------------------------------------------------------


def test_recipients_are_profiles_inside_the_fence_plus_all_authorities(setup: Setup) -> None:
    inside, outside, authority, far_authority = uuid4(), uuid4(), uuid4(), uuid4()
    setup.finder.locations = {inside: (-72.6, 2.0), outside: (-60.0, 2.0)}
    setup.finder.authorities = [authority, far_authority]

    setup.handler.handle(confirmed_event())

    [created] = setup.created
    assert {r.user_id for r in created.recipients} == {inside, authority, far_authority}
    assert outside not in {r.user_id for r in created.recipients}


def test_an_authority_inside_the_fence_is_listed_once_with_their_chat(setup: Setup) -> None:
    both = uuid4()
    setup.finder.locations = {both: (-72.6, 2.0)}
    setup.finder.authorities = [both]
    setup.finder.chats = {both: 777}

    setup.handler.handle(confirmed_event())

    [created] = setup.created
    assert created.recipients == (Recipient(both, 777),)


def test_select_recipients_prefers_the_entry_that_knows_the_chat() -> None:
    user = uuid4()
    chosen = select_recipients([Recipient(user, None)], [Recipient(user, 42)])
    assert chosen == [Recipient(user, 42)]
    assert select_recipients([], []) == []


def test_the_fence_follows_the_risk_level(setup: Setup) -> None:
    # ~15 km east of the area: inside the CRITICO fence (20 km), outside the BAJO one (2 km)
    near = uuid4()
    setup.finder.locations = {near: (-72.5 + 0.135, 2.0)}

    setup.handler.handle(confirmed_event(hectares=120.0))
    assert [r.user_id for r in setup.created[0].recipients] == [near]

    other = Setup()
    other.finder.locations = {near: (-72.5 + 0.135, 2.0)}
    other.handler.handle(confirmed_event(hectares=1.0))
    assert other.created[0].recipients == ()


def test_alert_carries_level_zone_and_type_for_the_notice(setup: Setup) -> None:
    setup.handler.handle(confirmed_event(anomaly_type="INCENDIO", hectares=38.0))
    [created] = setup.created
    assert created.risk_level == RiskLevel.HIGH.value
    assert (created.zone_name, created.anomaly_type, created.hectares) == (
        "Guaviare",
        "INCENDIO",
        38.0,
    )


# --- idempotency ------------------------------------------------------------------------------


def test_the_alert_id_is_derived_from_the_anomaly(setup: Setup) -> None:
    event = confirmed_event()
    setup.handler.handle(event)
    assert list(setup.alerts.rows) == [alert_id(event.anomaly_id)]
    assert setup.alerts.rows[alert_id(event.anomaly_id)].created_at == NOW


def test_repeating_the_event_neither_duplicates_the_alert_nor_renotifies(setup: Setup) -> None:
    event = confirmed_event()
    setup.finder.authorities = [uuid4()]

    for _ in range(3):
        setup.handler.handle(event)

    assert len(setup.alerts.rows) == 1
    assert len(setup.created) == 1


def test_different_anomalies_get_different_alerts(setup: Setup) -> None:
    setup.handler.handle(confirmed_event())
    setup.handler.handle(confirmed_event())
    assert len(setup.alerts.rows) == 2


# --- notification tolerance -------------------------------------------------------------------


def alert_created(*recipients: Recipient) -> AlertCreated:
    return AlertCreated(
        alert_id=uuid4(),
        risk_level="CRITICO",
        zone_name="Guaviare",
        anomaly_type="DEFORESTACION",
        hectares=120.0,
        recipients=recipients,
    )


def test_a_failing_channel_does_not_cancel_the_others(caplog: pytest.LogCaptureFixture) -> None:
    web = RecordingNotifier(Channel.WEB)
    broken = RecordingNotifier(Channel.TELEGRAM, fails=True)
    sms = RecordingNotifier(Channel.SMS)
    a, b = Recipient(uuid4(), 1), Recipient(uuid4(), 2)

    with caplog.at_level("ERROR"):
        NotifyAlertRecipients([web, broken, sms]).handle(alert_created(a, b))  # must not raise

    assert [r for r, _ in web.sent] == [a, b]
    assert [r for r, _ in sms.sent] == [a, b]
    assert broken.sent == []
    assert sum("TELEGRAM" in r.getMessage() for r in caplog.records) == 2  # logged per attempt


def test_notice_text_has_level_zone_hectares_and_public_link() -> None:
    alert = uuid4()
    notice = AlertNotice(alert, "CRITICO", "Guaviare", "DEFORESTACION", 120.0)
    text = compose_text(notice, "https://vigia.example/")
    assert "CRÍTICO" in text and "Guaviare" in text and "120.0 ha" in text
    assert "Deforestación" in text
    assert f"https://vigia.example/a/{alert}" in text


# --- event bus --------------------------------------------------------------------------------


def test_bus_delivers_by_event_type_and_survives_a_failing_handler(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bus = InMemoryEventBus()
    seen: list[AnomalyConfirmed] = []

    def broken(_: AnomalyConfirmed) -> None:
        raise RuntimeError("boom")

    bus.subscribe(AnomalyConfirmed, broken)
    bus.subscribe(AnomalyConfirmed, seen.append)
    bus.subscribe(AlertCreated, lambda e: pytest.fail("wrong event type"))

    event = confirmed_event()
    with caplog.at_level("ERROR"):
        bus.publish(event)
    assert seen == [event]
    assert "boom" in caplog.text


def test_full_chain_through_the_bus() -> None:
    """AnomalyConfirmed -> alert -> AlertCreated -> web + telegram notifications."""
    s = Setup()
    bus = InMemoryEventBus()
    web, telegram = RecordingNotifier(Channel.WEB), RecordingNotifier(Channel.TELEGRAM)
    handler = CreateAlertOnAnomalyConfirmed(s.alerts, s.finder, bus, clock=lambda: NOW)
    bus.subscribe(AnomalyConfirmed, handler.handle)
    bus.subscribe(AlertCreated, NotifyAlertRecipients([web, telegram]).handle)
    authority = uuid4()
    s.finder.authorities = [authority]

    event = confirmed_event()
    bus.publish(event)
    bus.publish(event)

    assert len(web.sent) == len(telegram.sent) == 1
    assert web.sent[0][0].user_id == authority
    assert web.sent[0][1].alert_id == alert_id(event.anomaly_id)


# --- confirm_anomaly --------------------------------------------------------------------------


def anomaly(zone: Zone, state: AnomalyState = AnomalyState.DETECTED) -> Anomaly:
    return Anomaly(
        id=uuid4(),
        zone_id=zone.id,
        type=AnomalyType.FIRE,
        magnitude=0.3,
        confidence=0.9,
        impact=ImpactEstimate(hectares=38.0, co2_tonnes=None),
        geometry=zone.geometry,
        detected_at=NOW,
        state=state,
    )


def confirm_setup(state: AnomalyState = AnomalyState.DETECTED):
    zone = Zone("Paramillo", "bosque_humedo_tropical", AREA, 0.15, 0.2)
    zones = InMemoryZoneRepository([zone])
    a = anomaly(zone, state)
    anomalies = InMemoryAnomalyRepository([a])
    publisher = RecordingPublisher()
    return ConfirmAnomaly(anomalies, zones, publisher), anomalies, publisher, a


def test_confirm_sets_the_state_and_publishes_the_event() -> None:
    use_case, anomalies, publisher, a = confirm_setup()

    result = use_case.execute(a.id)

    assert result.state is AnomalyState.CONFIRMED
    assert anomalies.rows[a.id].state is AnomalyState.CONFIRMED
    [event] = publisher.events
    assert isinstance(event, AnomalyConfirmed)
    assert (event.anomaly_id, event.zone_name, event.anomaly_type) == (
        a.id,
        "Paramillo",
        "INCENDIO",
    )
    assert event.hectares == 38.0 and event.confidence == 0.9


def test_confirming_again_republishes_so_a_failed_reaction_can_be_retried() -> None:
    use_case, _, publisher, a = confirm_setup(AnomalyState.CONFIRMED)
    use_case.execute(a.id)
    assert len(publisher.events) == 1


def test_a_false_positive_cannot_be_confirmed() -> None:
    use_case, anomalies, publisher, a = confirm_setup(AnomalyState.FALSE_POSITIVE)
    with pytest.raises(DomainValidationError):
        use_case.execute(a.id)
    assert publisher.events == []
    assert anomalies.rows[a.id].state is AnomalyState.FALSE_POSITIVE


def test_confirming_an_unknown_anomaly_is_not_found() -> None:
    use_case, _, publisher, _ = confirm_setup()
    with pytest.raises(NotFoundError):
        use_case.execute(UUID(int=1))
    assert publisher.events == []
