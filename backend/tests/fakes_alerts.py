"""In-memory fakes for the alerts and notifications ports (no DB, no network)."""

from typing import Any
from uuid import UUID

from shapely.geometry import Point, shape

from app.alerts.domain.alert import Alert, AlertDetail
from app.notifications.domain.notice import AlertNotice, Channel, NotificationDeliveryError
from app.shared.domain.errors import ConflictError, NotFoundError
from app.shared.domain.events import Recipient
from tests.fakes import InMemoryAnomalyRepository, InMemoryZoneRepository


class InMemoryAlertRepository:
    """Joins alerts with the in-memory anomalies/zones like the SQL read model does."""

    def __init__(self, anomalies: InMemoryAnomalyRepository, zones: InMemoryZoneRepository) -> None:
        self.rows: dict[UUID, Alert] = {}
        self._anomalies = anomalies
        self._zones = zones

    def add_if_absent(self, alert: Alert) -> bool:
        if alert.id in self.rows:
            return False
        self.rows[alert.id] = alert
        return True

    def _detail(self, alert: Alert) -> AlertDetail:
        anomaly = self._anomalies.rows[alert.anomaly_id]
        zone = self._zones.get(anomaly.zone_id)
        return AlertDetail(
            alert=alert,
            zone_id=anomaly.zone_id,
            zone_name=zone.name if zone else "—",
            anomaly_type=anomaly.type.value,
            confidence=anomaly.confidence,
            hectares=anomaly.impact.hectares,
            co2_tonnes=anomaly.impact.co2_tonnes,
            detected_at=anomaly.detected_at,
        )

    def get(self, alert_id: UUID) -> AlertDetail | None:
        alert = self.rows.get(alert_id)
        return self._detail(alert) if alert else None

    def find_all(self, limit: int) -> list[AlertDetail]:
        newest = sorted(self.rows.values(), key=lambda a: a.created_at, reverse=True)
        return [self._detail(a) for a in newest][:limit]


class FakeRecipientFinder:
    """Profiles with a location are matched against the fence geometrically (shapely)."""

    def __init__(self) -> None:
        self.locations: dict[UUID, tuple[float, float]] = {}  # user -> (lon, lat)
        self.authorities: list[UUID] = []
        self.chats: dict[UUID, int] = {}

    def _recipient(self, user_id: UUID) -> Recipient:
        return Recipient(user_id, self.chats.get(user_id))

    def find_within(self, geofence: dict[str, Any]) -> list[Recipient]:
        fence = shape(geofence)
        return [
            self._recipient(uid)
            for uid, (lon, lat) in self.locations.items()
            if fence.contains(Point(lon, lat))
        ]

    def find_authorities(self) -> list[Recipient]:
        return [self._recipient(uid) for uid in self.authorities]


class RecordingNotifier:
    def __init__(self, channel: Channel, *, fails: bool = False) -> None:
        self.channel = channel
        self.fails = fails
        self.sent: list[tuple[Recipient, AlertNotice]] = []

    def send(self, recipient: Recipient, notice: AlertNotice) -> None:
        if self.fails:
            raise NotificationDeliveryError("canal caído")
        self.sent.append((recipient, notice))


class RecordingPublisher:
    def __init__(self) -> None:
        self.events: list[object] = []

    def publish(self, event: object) -> None:
        self.events.append(event)


class InMemoryChatLinkRepository:
    def __init__(self, known_users: set[UUID] | None = None) -> None:
        self.known_users = known_users  # None = every user exists
        self.chats: dict[UUID, int] = {}

    def link(self, user_id: UUID, chat_id: int) -> None:
        if self.known_users is not None and user_id not in self.known_users:
            raise NotFoundError("No existe el perfil del usuario.")
        if any(c == chat_id and u != user_id for u, c in self.chats.items()):
            raise ConflictError("Ese chat de Telegram ya está vinculado a otra cuenta.")
        self.chats[user_id] = chat_id


class FakeTelegramChat:
    def __init__(self, *, fails: bool = False) -> None:
        self.fails = fails
        self.sent: list[tuple[int, str]] = []

    def send_text(self, chat_id: int, text: str) -> None:
        if self.fails:
            raise NotificationDeliveryError("sin red")
        self.sent.append((chat_id, text))
