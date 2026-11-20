"""Before/after satellite images: use case (fakes), demo renderer, Sentinel adapter, endpoint."""

import io
import json
from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.monitoring.adapters.outbound.satellite.demo_image import render_demo_image
from app.monitoring.adapters.outbound.satellite.demo_satellite_adapter import (
    DemoSatelliteIndexAdapter,
)
from app.monitoring.adapters.outbound.satellite.sentinel_hub_adapter import (
    CDSE_PROCESS_URL,
    CDSE_TOKEN_URL,
    SentinelHubStatisticalAdapter,
    image_size,
)
from app.monitoring.application.use_cases.ensure_anomaly_images import EnsureAnomalyImages
from app.monitoring.domain.anomaly import Anomaly, AnomalyType
from app.monitoring.domain.geo import BBox
from app.monitoring.domain.images import ImagePhase, image_path, image_requests
from app.monitoring.domain.impact import ImpactEstimate
from app.monitoring.domain.zone import Zone
from app.shared.adapters.outbound.storage.in_memory_storage import InMemoryStorage
from app.shared.domain.errors import NotFoundError, ServiceUnavailableError
from app.shared.domain.user import Role
from tests.conftest import TokenFactory
from tests.fakes import InMemoryAnomalyRepository, InMemoryProfileRepository, InMemoryZoneRepository
from tests.test_scan_api import bearer
from tests.test_zones_use_cases import square

DETECTED = datetime(2026, 11, 15, 9, tzinfo=UTC)
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
AREA = square(-72.8, 1.85, 0.3)


class FakeImageSatellite:
    """Returns a PNG per request; days in `failing_days` raise like a provider outage."""

    def __init__(self) -> None:
        self.calls: list[tuple[date, int]] = []
        self.failing_days: set[date] = set()
        self.payload = PNG

    async def get_image(
        self, geometry: dict[str, Any], day: date, lookback_days: int = 10
    ) -> bytes:
        self.calls.append((day, lookback_days))
        if day in self.failing_days:
            raise ServiceUnavailableError("provider down")
        return self.payload


class BrokenStorage(InMemoryStorage):
    def upload(self, path: str, data: bytes, content_type: str, *, overwrite: bool = False) -> None:
        if path.endswith("antes.png"):
            raise ServiceUnavailableError("storage down")
        super().upload(path, data, content_type, overwrite=overwrite)


def make_anomaly(repo: InMemoryAnomalyRepository) -> Anomaly:
    anomaly = Anomaly(
        id=uuid4(),
        zone_id=uuid4(),
        type=AnomalyType.DEFORESTATION,
        magnitude=0.3,
        confidence=0.9,
        impact=ImpactEstimate(hectares=120.0, co2_tonnes=None),
        geometry=AREA,
        detected_at=DETECTED,
    )
    repo.save(anomaly)
    return anomaly


class Setup:
    def __init__(self, storage: InMemoryStorage | None = None) -> None:
        self.anomalies = InMemoryAnomalyRepository()
        self.satellite = FakeImageSatellite()
        self.storage = storage or InMemoryStorage()
        self.use_case = EnsureAnomalyImages(self.anomalies, self.satellite, self.storage)
        self.anomaly = make_anomaly(self.anomalies)

    @property
    def before_day(self) -> date:
        return image_requests(DETECTED)[0].day

    @property
    def stored(self) -> Anomaly:
        return self.anomalies.rows[self.anomaly.id]


@pytest.fixture
def setup() -> Setup:
    return Setup()


# --- the use case ---------------------------------------------------------------------------------


async def test_images_are_generated_stored_and_signed_on_first_request(setup: Setup) -> None:
    images = await setup.use_case.execute(setup.anomaly.id)

    before_path = image_path(setup.anomaly.id, ImagePhase.BEFORE)
    after_path = image_path(setup.anomaly.id, ImagePhase.AFTER)
    assert before_path == f"anomalias/{setup.anomaly.id}/antes.png"
    assert set(setup.storage.objects) == {before_path, after_path}
    assert all(data == PNG for data, _ in setup.storage.objects.values())
    assert setup.stored.before_image_path == before_path  # a path, not a URL
    assert setup.stored.after_image_path == after_path
    assert images.before_url and images.before_url.endswith("expires_in=3600")
    assert images.after_url and "despues.png" in images.after_url
    assert images.before_date == date(2026, 10, 16)  # detection day minus 30
    assert images.after_date == DETECTED.date()
    assert (DETECTED.date() - images.before_date).days == 30


async def test_before_and_after_ask_for_different_scenes(setup: Setup) -> None:
    await setup.use_case.execute(setup.anomaly.id)
    (before_day, before_look), (after_day, after_look) = setup.satellite.calls
    assert before_day < after_day and (before_look, after_look) == (15, 10)


async def test_existing_images_are_reused_and_never_regenerated(setup: Setup) -> None:
    first = await setup.use_case.execute(setup.anomaly.id)
    calls_after_first = len(setup.satellite.calls)
    uploads = dict(setup.storage.objects)

    second = await setup.use_case.execute(setup.anomaly.id)
    third = await setup.use_case.execute(setup.anomaly.id)

    assert len(setup.satellite.calls) == calls_after_first == 2  # the provider was not called again
    assert setup.storage.objects == uploads
    assert second.before_url == first.before_url and third.after_url == first.after_url


async def test_one_failing_image_does_not_lose_the_other_and_is_retried_alone(
    setup: Setup,
) -> None:
    setup.satellite.failing_days = {setup.before_day}

    partial = await setup.use_case.execute(setup.anomaly.id)

    assert partial.before_url is None and partial.after_url is not None
    assert setup.stored.before_image_path is None
    assert setup.stored.after_image_path == image_path(setup.anomaly.id, ImagePhase.AFTER)
    assert len(setup.storage.objects) == 1

    setup.satellite.failing_days = set()
    setup.satellite.calls.clear()
    healed = await setup.use_case.execute(setup.anomaly.id)

    assert healed.before_url is not None and healed.after_url is not None
    assert [day for day, _ in setup.satellite.calls] == [setup.before_day]  # only the missing one
    assert len(setup.storage.objects) == 2


async def test_a_storage_failure_on_one_image_is_a_partial_failure_too() -> None:
    setup = Setup(BrokenStorage())
    result = await setup.use_case.execute(setup.anomaly.id)
    assert result.before_url is None and result.after_url is not None
    assert setup.stored.before_image_path is None  # never records a path that was not stored


async def test_when_both_fail_it_raises_and_saves_nothing(setup: Setup) -> None:
    before, after = image_requests(DETECTED)
    setup.satellite.failing_days = {before.day, after.day}
    with pytest.raises(ServiceUnavailableError):
        await setup.use_case.execute(setup.anomaly.id)
    assert setup.storage.objects == {}
    assert (setup.stored.before_image_path, setup.stored.after_image_path) == (None, None)


async def test_a_provider_answer_that_is_not_a_png_is_a_failure(setup: Setup) -> None:
    setup.satellite.payload = b"<html>error</html>"
    with pytest.raises(ServiceUnavailableError):
        await setup.use_case.execute(setup.anomaly.id)
    assert setup.storage.objects == {}


async def test_unknown_anomaly_is_not_found(setup: Setup) -> None:
    with pytest.raises(NotFoundError):
        await setup.use_case.execute(uuid4())
    assert setup.satellite.calls == []


async def test_a_stale_object_from_a_rolled_back_attempt_does_not_block_the_retry(
    setup: Setup,
) -> None:
    # the object exists in storage but the DB never recorded its path (transaction rolled back)
    setup.storage.objects[image_path(setup.anomaly.id, ImagePhase.BEFORE)] = (b"stale", "image/png")
    images = await setup.use_case.execute(setup.anomaly.id)
    assert images.before_url is not None
    assert setup.storage.objects[image_path(setup.anomaly.id, ImagePhase.BEFORE)][0] == PNG


# --- the demo renderer ----------------------------------------------------------------------------


def test_demo_image_is_a_deterministic_png() -> None:
    day = date(2026, 11, 15)
    first, again = render_demo_image(AREA, day), render_demo_image(AREA, day)
    assert first == again
    image = Image.open(io.BytesIO(first))
    assert image.format == "PNG" and image.size[0] > 0 and image.size[1] > 0


def test_demo_before_and_after_images_differ() -> None:
    before = render_demo_image(AREA, date(2026, 10, 16))
    after = render_demo_image(AREA, date(2026, 11, 15))
    assert before != after
    other_area = render_demo_image(square(-76.2, 7.0, 0.35), date(2026, 11, 15))
    assert other_area != after


async def test_the_demo_satellite_adapter_serves_the_renderer() -> None:
    adapter = DemoSatelliteIndexAdapter()
    assert await adapter.get_image(AREA, date(2026, 11, 15)) == render_demo_image(
        AREA, date(2026, 11, 15)
    )


# --- the Sentinel Hub adapter (Process API) --------------------------------------------------------


def sentinel(handler) -> SentinelHubStatisticalAdapter:
    return SentinelHubStatisticalAdapter(
        "client-id", "client-secret", transport=httpx.MockTransport(handler), backoff_s=0
    )


async def test_sentinel_process_request_uses_least_cloud_mosaic_and_cloud_mask() -> None:
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        if str(request.url) == CDSE_TOKEN_URL:
            return httpx.Response(200, json={"access_token": "T", "expires_in": 300})
        seen.append(request)
        return httpx.Response(200, content=PNG, headers={"content-type": "image/png"})

    png = await sentinel(respond).get_image(AREA, date(2026, 11, 15), lookback_days=10)

    assert png == PNG
    [request] = seen
    assert str(request.url) == CDSE_PROCESS_URL
    assert request.headers["authorization"] == "Bearer T"  # same OAuth client as the statistics
    assert request.headers["accept"] == "image/png"
    body = json.loads(request.content)
    data = body["input"]["data"][0]
    assert data["type"] == "sentinel-2-l2a"
    assert data["dataFilter"]["mosaickingOrder"] == "leastCC"
    assert data["dataFilter"]["timeRange"] == {
        "from": "2026-11-05T00:00:00Z",
        "to": "2026-11-15T23:59:59Z",
    }
    assert body["input"]["bounds"]["geometry"] == AREA
    assert "SCL" in body["evalscript"] and "MASKED_SCL" in body["evalscript"]
    assert body["output"]["responses"][0]["format"]["type"] == "image/png"
    assert 0 < body["output"]["width"] <= 768 and 0 < body["output"]["height"] <= 768


async def test_sentinel_rejects_a_non_png_answer_and_missing_credentials() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if str(request.url) == CDSE_TOKEN_URL:
            return httpx.Response(200, json={"access_token": "T", "expires_in": 300})
        return httpx.Response(200, content=b"not an image")

    with pytest.raises(ServiceUnavailableError, match="PNG"):
        await sentinel(respond).get_image(AREA, date(2026, 11, 15))

    unconfigured = SentinelHubStatisticalAdapter("", "")
    with pytest.raises(ServiceUnavailableError, match="SENTINEL"):
        await unconfigured.get_image(AREA, date(2026, 11, 15))


async def test_sentinel_provider_error_is_service_unavailable() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if str(request.url) == CDSE_TOKEN_URL:
            return httpx.Response(200, json={"access_token": "T", "expires_in": 300})
        return httpx.Response(400, json={"error": "bad"})

    with pytest.raises(ServiceUnavailableError):
        await sentinel(respond).get_image(AREA, date(2026, 11, 15))


def test_image_size_keeps_the_aspect_ratio_and_the_limits() -> None:
    wide = image_size(BBox(-72.8, 1.85, -72.2, 1.95))  # ~66 km x 11 km
    assert wide[0] == 768 and wide[1] < wide[0]
    tall = image_size(BBox(-72.8, 1.0, -72.7, 3.0))
    assert tall[1] == 768 and tall[0] < tall[1]
    tiny = image_size(BBox(-72.8, 1.85, -72.7999, 1.8501))
    assert min(tiny) >= 32


# --- GET /api/anomalies/{id}/images ----------------------------------------------------------------


@pytest.fixture
def stored_anomaly(anomalies: InMemoryAnomalyRepository, zones: InMemoryZoneRepository) -> Anomaly:
    zones.add(Zone("Guaviare", "bosque_amazonico", AREA, 0.15, 0.2))
    return make_anomaly(anomalies)


def test_images_endpoint_requires_authentication(
    client: TestClient, stored_anomaly: Anomaly
) -> None:
    assert client.get(f"/api/anomalies/{stored_anomaly.id}/images").status_code == 401


def test_images_endpoint_returns_two_signed_urls_and_caches_them(
    client: TestClient,
    profiles: InMemoryProfileRepository,
    make_token: TokenFactory,
    stored_anomaly: Anomaly,
    anomalies: InMemoryAnomalyRepository,
    storage: InMemoryStorage,
) -> None:
    user = uuid4()
    profiles.roles[user] = Role.CIUDADANO
    url = f"/api/anomalies/{stored_anomaly.id}/images"

    r = client.get(url, headers=bearer(make_token(user)))

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["before_url"].startswith("https://storage.demo.invalid/evidencias/anomalias/")
    assert "antes.png" in body["before_url"] and "despues.png" in body["after_url"]
    assert body["after_date"] == "2026-11-15" and body["before_date"] == "2026-10-16"
    stored = anomalies.rows[stored_anomaly.id]
    assert stored.before_image_path and stored.after_image_path  # paths persisted
    snapshot = dict(storage.objects)
    for data, content_type in snapshot.values():
        assert data.startswith(b"\x89PNG") and content_type == "image/png"

    again = client.get(url, headers=bearer(make_token(user)))
    assert again.json() == body and storage.objects == snapshot  # nothing regenerated


def test_images_endpoint_unknown_anomaly_is_404(
    client: TestClient, make_token: TokenFactory, profiles: InMemoryProfileRepository
) -> None:
    user = uuid4()
    profiles.roles[user] = Role.CIUDADANO
    r = client.get(f"/api/anomalies/{uuid4()}/images", headers=bearer(make_token(user)))
    assert r.status_code == 404 and r.headers["content-type"] == "application/problem+json"
    assert (
        client.get("/api/anomalies/not-a-uuid/images", headers=bearer(make_token(user))).status_code
        == 422
    )
