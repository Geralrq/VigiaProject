from uuid import uuid4

from fastapi.testclient import TestClient

from app.shared.domain.user import Role
from tests.conftest import TokenFactory
from tests.fakes import InMemoryProfileRepository, InMemoryZoneRepository
from tests.test_zones_use_cases import square

PROBLEM = "application/problem+json"
NEW_ZONE = {
    "name": "PNN Paramillo",
    "cover_type": "bosque_humedo_tropical",
    "geometry": square(),
    "ndvi_threshold": 0.15,
    "nbr_threshold": 0.2,
}


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_missing_token_is_401_problem(client: TestClient) -> None:
    r = client.get("/api/zones")
    assert r.status_code == 401
    assert r.headers["content-type"] == PROBLEM
    assert r.headers["www-authenticate"] == "Bearer"
    body = r.json()
    assert body["status"] == 401 and body["title"] == "No autenticado"
    assert body["instance"] == "/api/zones"


def test_expired_token_is_401(client: TestClient, make_token: TokenFactory) -> None:
    r = client.get("/api/zones", headers=bearer(make_token(expires_in=-120)))
    assert r.status_code == 401
    assert "expiró" in r.json()["detail"]


def test_wrong_audience_is_401(client: TestClient, make_token: TokenFactory) -> None:
    r = client.get("/api/zones", headers=bearer(make_token(aud="anon")))
    assert r.status_code == 401


def test_first_sign_in_lists_zones_and_creates_citizen(
    client: TestClient, make_token: TokenFactory, profiles: InMemoryProfileRepository
) -> None:
    sub = uuid4()
    r = client.get("/api/zones", headers=bearer(make_token(sub)))
    assert r.status_code == 200
    assert r.json() == []
    assert profiles.roles[sub] is Role.CIUDADANO


def test_citizen_cannot_create_zone(client: TestClient, make_token: TokenFactory) -> None:
    r = client.post("/api/zones", json=NEW_ZONE, headers=bearer(make_token()))
    assert r.status_code == 403
    assert r.headers["content-type"] == PROBLEM
    assert "ADMIN" in r.json()["detail"]


def test_role_claims_in_token_are_ignored(
    client: TestClient, make_token: TokenFactory, profiles: InMemoryProfileRepository
) -> None:
    sub = uuid4()
    profiles.roles[sub] = Role.CIUDADANO
    forged = make_token(sub, role="ADMIN", user_role="ADMIN", app_metadata={"role": "ADMIN"})
    r = client.post("/api/zones", json=NEW_ZONE, headers=bearer(forged))
    assert r.status_code == 403


def test_admin_creates_zone_and_gets_geojson_back(
    client: TestClient,
    make_token: TokenFactory,
    profiles: InMemoryProfileRepository,
    zones: InMemoryZoneRepository,
) -> None:
    admin = uuid4()
    profiles.roles[admin] = Role.ADMIN
    r = client.post("/api/zones", json=NEW_ZONE, headers=bearer(make_token(admin)))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["geometry"] == NEW_ZONE["geometry"]
    assert body["active"] is True
    assert [z.name for z in zones.zones] == ["PNN Paramillo"]

    listed = client.get("/api/zones", headers=bearer(make_token(admin))).json()
    assert [z["id"] for z in listed] == [body["id"]]


def test_invalid_body_is_422_problem(
    client: TestClient, make_token: TokenFactory, profiles: InMemoryProfileRepository
) -> None:
    admin = uuid4()
    profiles.roles[admin] = Role.ADMIN
    r = client.post(
        "/api/zones", json=NEW_ZONE | {"ndvi_threshold": 7}, headers=bearer(make_token(admin))
    )
    assert r.status_code == 422
    assert r.headers["content-type"] == PROBLEM
    assert r.json()["errors"][0]["loc"] == ["body", "ndvi_threshold"]


def test_domain_rule_violation_is_422_problem(
    client: TestClient, make_token: TokenFactory, profiles: InMemoryProfileRepository
) -> None:
    admin = uuid4()
    profiles.roles[admin] = Role.ADMIN
    open_ring = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1]]]}
    r = client.post(
        "/api/zones", json=NEW_ZONE | {"geometry": open_ring}, headers=bearer(make_token(admin))
    )
    assert r.status_code == 422
    assert "cerrarse" in r.json()["detail"]


def test_unknown_route_is_404_problem(client: TestClient) -> None:
    r = client.get("/api/nope")
    assert r.status_code == 404
    assert r.headers["content-type"] == PROBLEM


def test_cors_preflight_allows_local_frontend(client: TestClient) -> None:
    r = client.options(
        "/api/zones",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_rejects_other_origins(client: TestClient) -> None:
    r = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers
