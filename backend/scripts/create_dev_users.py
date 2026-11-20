"""Idempotent dev users for local login. Run from /backend:  uv run python -m scripts.create_dev_users

Only runs with APP_MODE=demo. Creates (or finds) five confirmed users in Supabase Auth through
the Admin API with the service key, and upserts their `profiles` row (same id as auth, matching
role, es_demo=false). The password comes from DEV_USERS_PASSWORD in .env.local and is never
printed. Re-running neither duplicates users nor resets points or passwords.
"""

import sys
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

import httpx
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.shared.adapters.outbound.persistence.engine import build_engine
from app.shared.adapters.outbound.persistence.models import ProfileModel
from app.shared.settings import get_settings
from scripts.seed import ZONES

TIMEOUT = httpx.Timeout(30.0, connect=10.0)
PAGE_SIZE = 200


def _zone_center(key: str) -> tuple[float, float]:
    for zone_key, *_rest, bounds, _u_ndvi, _u_nbr in ZONES:
        if zone_key == key:
            min_lon, min_lat, max_lon, max_lat = bounds
            return (min_lon + max_lon) / 2, (min_lat + max_lat) / 2
    raise KeyError(key)


def _near(center: tuple[float, float], d_lon: float, d_lat: float) -> tuple[float, float]:
    return center[0] + d_lon, center[1] + d_lat


# ~110 m from the centre of the demo zones (Guaviare deforestation, Paramillo fire): closer than
# the seed's demo volunteers (1.5-7 km), so they are among the 5 nearest when an anomaly appears.
# Only these two roles receive verification missions; the other three have no location.
DEV_USERS: list[tuple[str, str, str, tuple[float, float] | None]] = [
    (
        "ciudadano@vigia.test",
        "Ciudadano Dev",
        "CIUDADANO",
        _near(_zone_center("guaviare"), 0.001, 0),
    ),
    (
        "guardabosques@vigia.test",
        "Guardabosques Dev",
        "GUARDABOSQUES",
        _near(_zone_center("paramillo"), 0.001, 0),
    ),
    ("tecnico@vigia.test", "Tecnico Dev", "TECNICO", None),
    ("autoridad@vigia.test", "Autoridad Dev", "AUTORIDAD", None),
    ("admin@vigia.test", "Admin Dev", "ADMIN", None),
]


class AuthAdmin(Protocol):
    def find_user_id(self, email: str) -> UUID | None: ...

    def create_user(self, email: str, password: str) -> UUID: ...


class ProfileWriter(Protocol):
    def upsert(
        self, user_id: UUID, nombre: str, rol: str, location: tuple[float, float] | None
    ) -> None: ...


@dataclass(frozen=True)
class DevUserResult:
    email: str
    role: str
    created: bool


class DevUsersError(Exception):
    """A failure that is safe to show (never carries keys or the password)."""


class SupabaseAuthAdmin:
    """Supabase Auth Admin API (GoTrue) with the service key."""

    def __init__(
        self, supabase_url: str, service_key: str, *, transport: httpx.BaseTransport | None = None
    ) -> None:
        self._root = f"{supabase_url.rstrip('/')}/auth/v1/admin/users"
        headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}
        self._client = httpx.Client(timeout=TIMEOUT, headers=headers, transport=transport)

    def find_user_id(self, email: str) -> UUID | None:
        wanted = email.lower()
        page = 1
        while True:
            body = self._request("GET", params={"page": page, "per_page": PAGE_SIZE}).json()
            users = body.get("users", [])
            for user in users:
                if str(user.get("email", "")).lower() == wanted:
                    return UUID(user["id"])
            if len(users) < PAGE_SIZE:
                return None
            page += 1

    def create_user(self, email: str, password: str) -> UUID:
        body = {"email": email, "password": password, "email_confirm": True}
        return UUID(self._request("POST", json=body).json()["id"])

    def _request(self, method: str, **kwargs) -> httpx.Response:
        try:
            response = self._client.request(method, self._root, **kwargs)
        except httpx.HTTPError as exc:
            raise DevUsersError(f"Auth Admin API unreachable ({type(exc).__name__})") from None
        if response.status_code >= 400:
            code = ""
            try:
                code = str(response.json().get("error_code", ""))
            except ValueError:
                pass
            raise DevUsersError(
                f"Auth Admin API rejected {method}: HTTP {response.status_code} {code}"
            )
        return response


class SqlProfileWriter:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert(
        self, user_id: UUID, nombre: str, rol: str, location: tuple[float, float] | None
    ) -> None:
        ubicacion = from_shape(Point(*location), srid=4326) if location else None
        values = {"nombre": nombre, "rol": rol, "ubicacion": ubicacion, "es_demo": False}
        self._session.execute(
            insert(ProfileModel)
            .values(id=user_id, **values)  # puntos keep their value on conflict
            .on_conflict_do_update(index_elements=["id"], set_=values)
        )


def ensure_demo_mode(app_mode: str) -> None:
    if app_mode != "demo":
        raise DevUsersError("create_dev_users only runs with APP_MODE=demo.")


def create_dev_users(
    auth: AuthAdmin, profiles: ProfileWriter, password: str, *, app_mode: str
) -> list[DevUserResult]:
    ensure_demo_mode(app_mode)
    if not password:
        raise DevUsersError("DEV_USERS_PASSWORD is empty: set it in .env.local.")
    results: list[DevUserResult] = []
    for email, nombre, rol, location in DEV_USERS:
        user_id = auth.find_user_id(email)
        created = user_id is None
        if user_id is None:
            user_id = auth.create_user(email, password)
        profiles.upsert(user_id, nombre, rol, location)
        results.append(DevUserResult(email, rol, created))
    return results


def main() -> None:
    settings = get_settings()
    try:
        ensure_demo_mode(settings.app_mode)
        key = settings.supabase_service_key.get_secret_value()
        if not (settings.supabase_url and key):
            raise DevUsersError("SUPABASE_URL / SUPABASE_SERVICE_KEY are not set in .env.local.")
        auth = SupabaseAuthAdmin(settings.supabase_url, key)
        engine = build_engine(settings.database_url.get_secret_value())
        with Session(engine) as session, session.begin():
            results = create_dev_users(
                auth,
                SqlProfileWriter(session),
                settings.dev_users_password.get_secret_value(),
                app_mode=settings.app_mode,
            )
    except DevUsersError as exc:
        print(f"[FAIL] {exc}")
        sys.exit(1)
    for r in results:
        print(f"{'creado   ' if r.created else 'existente'}  {r.email}  {r.role}")


if __name__ == "__main__":
    main()
