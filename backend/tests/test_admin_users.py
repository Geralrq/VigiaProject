import logging
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.shared.application.use_cases.manage_users import ChangeRoleCommand, ChangeUserRole
from app.shared.domain.errors import ConflictError, DomainValidationError, NotFoundError
from app.shared.domain.profile import GeoPoint
from app.shared.domain.user import Role
from app.shared.domain.user_admin import UserQuery
from tests.conftest import TokenFactory
from tests.fakes import InMemoryProfileRepository
from tests.fakes_profile import InMemoryMyProfileRepository, InMemoryUserAdminRepository

PEOPLE = [
    ("admin", Role.ADMIN),
    ("admin2", Role.ADMIN),
    ("boss", Role.AUTORIDAD),
    ("tec", Role.TECNICO),
    ("ranger", Role.GUARDABOSQUES),
    ("ana", Role.CIUDADANO),
    ("anabel", Role.CIUDADANO),
]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def ids(profiles: InMemoryProfileRepository, my_profiles: InMemoryMyProfileRepository) -> dict:
    ids = {name: uuid4() for name, _ in PEOPLE}
    for name, role in PEOPLE:
        profiles.roles[ids[name]] = role
        profiles.names[ids[name]] = name.capitalize()
    my_profiles.locations[ids["ana"]] = GeoPoint(2.5, -72.6)
    my_profiles.chats[ids["ana"]] = 123456789
    my_profiles.points[ids["ana"]] = 15
    return ids


@pytest.fixture
def admin_headers(ids: dict, make_token: TokenFactory) -> dict[str, str]:
    return bearer(make_token(ids["admin"]))


# --- listing -----------------------------------------------------------------------------


def test_admin_lists_with_flags_but_no_location_or_chat(
    client: TestClient, ids: dict, admin_headers: dict
) -> None:
    r = client.get("/api/admin/users", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == len(PEOPLE) and body["page"] == 1 and body["page_size"] == 20
    ana = next(u for u in body["items"] if u["id"] == str(ids["ana"]))
    assert ana == {
        "id": str(ids["ana"]),
        "name": "Ana",
        "role": "CIUDADANO",
        "points": 15,
        "created_at": ana["created_at"],
        "has_location": True,
        "telegram_linked": True,
    }
    assert "123456789" not in r.text and "-72.6" not in r.text
    others = [u for u in body["items"] if u["id"] != str(ids["ana"])]
    assert not any(u["has_location"] or u["telegram_linked"] for u in others)


def test_search_by_name_is_case_insensitive_and_filters_by_role(
    client: TestClient, admin_headers: dict
) -> None:
    r = client.get("/api/admin/users", params={"q": "  ANA "}, headers=admin_headers)
    assert [u["name"] for u in r.json()["items"]] == ["Ana", "Anabel"]
    r = client.get("/api/admin/users", params={"rol": "ADMIN"}, headers=admin_headers)
    assert [u["name"] for u in r.json()["items"]] == ["Admin", "Admin2"]
    r = client.get("/api/admin/users", params={"q": "ana", "rol": "ADMIN"}, headers=admin_headers)
    assert r.json() == {"items": [], "total": 0, "page": 1, "page_size": 20}


def test_pagination(client: TestClient, admin_headers: dict) -> None:
    r = client.get("/api/admin/users", params={"page": 2, "page_size": 3}, headers=admin_headers)
    body = r.json()
    assert body["total"] == len(PEOPLE) and body["page"] == 2
    assert [u["name"] for u in body["items"]] == ["Anabel", "Boss", "Ranger"]


@pytest.mark.parametrize(
    "params",
    [{"page": 0}, {"page_size": 0}, {"page_size": 101}, {"rol": "JEFE"}, {"q": "x" * 201}],
)
def test_invalid_listing_params(client: TestClient, admin_headers: dict, params: dict) -> None:
    r = client.get("/api/admin/users", params=params, headers=admin_headers)
    assert r.status_code == 422
    assert r.headers["content-type"] == "application/problem+json"


def test_query_validation_in_domain() -> None:
    assert UserQuery(search="   ").search is None
    with pytest.raises(DomainValidationError):
        UserQuery(page=0)
    with pytest.raises(DomainValidationError):
        UserQuery(page_size=500)


# --- permissions ------------------------------------------------------------------------


@pytest.mark.parametrize("who", ["boss", "tec", "ranger", "ana"])
def test_only_admin_can_list_or_change_roles(
    client: TestClient, ids: dict, make_token: TokenFactory, who: str
) -> None:
    headers = bearer(make_token(ids[who]))
    assert client.get("/api/admin/users", headers=headers).status_code == 403
    r = client.patch(f"/api/admin/users/{ids['tec']}/rol", json={"rol": "ADMIN"}, headers=headers)
    assert r.status_code == 403
    assert r.headers["content-type"] == "application/problem+json"


def test_requires_authentication(client: TestClient, ids: dict) -> None:
    assert client.get("/api/admin/users").status_code == 401
    r = client.patch(f"/api/admin/users/{ids['tec']}/rol", json={"rol": "ADMIN"})
    assert r.status_code == 401


# --- changing roles ---------------------------------------------------------------------


def test_admin_changes_a_role_and_it_is_logged(
    client: TestClient,
    ids: dict,
    admin_headers: dict,
    profiles: InMemoryProfileRepository,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="app.shared.application.use_cases.manage_users"):
        r = client.patch(
            f"/api/admin/users/{ids['ana']}/rol",
            json={"rol": "GUARDABOSQUES"},
            headers=admin_headers,
        )
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "GUARDABOSQUES"
    assert profiles.roles[ids["ana"]] is Role.GUARDABOSQUES
    messages = [rec.getMessage() for rec in caplog.records]
    assert any(
        str(ids["admin"]) in m and str(ids["ana"]) in m and "CIUDADANO -> GUARDABOSQUES" in m
        for m in messages
    ), messages


def test_an_admin_can_demote_another_admin(
    client: TestClient, ids: dict, admin_headers: dict, profiles: InMemoryProfileRepository
) -> None:
    r = client.patch(
        f"/api/admin/users/{ids['admin2']}/rol", json={"rol": "TECNICO"}, headers=admin_headers
    )
    assert r.status_code == 200, r.text
    assert profiles.roles[ids["admin2"]] is Role.TECNICO


@pytest.mark.parametrize("body", [{"rol": "JEFE"}, {"rol": "admin"}, {}, {"rol": "ADMIN", "x": 1}])
def test_invalid_role_body(client: TestClient, ids: dict, admin_headers: dict, body: dict) -> None:
    r = client.patch(f"/api/admin/users/{ids['tec']}/rol", json=body, headers=admin_headers)
    assert r.status_code == 422
    assert r.headers["content-type"] == "application/problem+json"


def test_cannot_change_own_role(
    client: TestClient, ids: dict, admin_headers: dict, profiles: InMemoryProfileRepository
) -> None:
    r = client.patch(
        f"/api/admin/users/{ids['admin']}/rol", json={"rol": "CIUDADANO"}, headers=admin_headers
    )
    assert r.status_code == 409
    assert r.headers["content-type"] == "application/problem+json"
    assert "propio rol" in r.json()["detail"]
    assert profiles.roles[ids["admin"]] is Role.ADMIN


def test_unknown_user_is_404(client: TestClient, admin_headers: dict) -> None:
    r = client.patch(
        f"/api/admin/users/{uuid4()}/rol", json={"rol": "TECNICO"}, headers=admin_headers
    )
    assert r.status_code == 404
    assert r.headers["content-type"] == "application/problem+json"
    assert (
        client.patch(
            "/api/admin/users/no-es-uuid/rol", json={"rol": "TECNICO"}, headers=admin_headers
        ).status_code
        == 422
    )


def test_same_role_is_a_no_op_without_log(
    ids: dict, user_admin: InMemoryUserAdminRepository, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        user = ChangeUserRole(user_admin).execute(
            ChangeRoleCommand(ids["admin"], ids["tec"], Role.TECNICO)
        )
    assert user.role is Role.TECNICO
    assert not [r for r in caplog.records if "Role changed" in r.getMessage()]


def _single_admin(profiles: InMemoryProfileRepository) -> tuple[UUID, UUID]:
    """One ADMIN left; the caller (already authorised) was demoted by a concurrent request."""
    last, caller = uuid4(), uuid4()
    profiles.roles.update({last: Role.ADMIN, caller: Role.TECNICO})
    return last, caller


@pytest.mark.parametrize("new_role", [r for r in Role if r is not Role.ADMIN])
def test_the_last_admin_cannot_be_demoted(
    profiles: InMemoryProfileRepository, user_admin: InMemoryUserAdminRepository, new_role: Role
) -> None:
    last, caller = _single_admin(profiles)
    with pytest.raises(ConflictError, match="último administrador"):
        ChangeUserRole(user_admin).execute(ChangeRoleCommand(caller, last, new_role))
    assert profiles.roles[last] is Role.ADMIN


def test_last_admin_rule_still_allows_promotions(
    profiles: InMemoryProfileRepository, user_admin: InMemoryUserAdminRepository
) -> None:
    last, caller = _single_admin(profiles)
    other = uuid4()
    profiles.roles[other] = Role.CIUDADANO
    ChangeUserRole(user_admin).execute(ChangeRoleCommand(last, other, Role.ADMIN))
    assert profiles.roles[other] is Role.ADMIN
    # with two admins now, the former last one can be demoted by the other
    ChangeUserRole(user_admin).execute(ChangeRoleCommand(other, last, Role.AUTORIDAD))
    assert profiles.roles[last] is Role.AUTORIDAD
    assert caller in profiles.roles


def test_admins_are_locked_before_the_target(
    ids: dict, user_admin: InMemoryUserAdminRepository
) -> None:
    ChangeUserRole(user_admin).execute(ChangeRoleCommand(ids["admin"], ids["tec"], Role.AUTORIDAD))
    assert user_admin.locked == ["admins", f"user:{ids['tec']}"]


def test_unknown_user_in_use_case(user_admin: InMemoryUserAdminRepository) -> None:
    with pytest.raises(NotFoundError):
        ChangeUserRole(user_admin).execute(ChangeRoleCommand(uuid4(), uuid4(), Role.TECNICO))
