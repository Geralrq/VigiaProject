from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.shared.application.use_cases.list_users import ListUsersByRole
from app.shared.domain.errors import DomainValidationError
from app.shared.domain.user import Role
from tests.conftest import TokenFactory
from tests.fakes import InMemoryProfileRepository
from tests.fakes_profile import InMemoryUserDirectory


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def seed(profiles: InMemoryProfileRepository) -> dict[str, object]:
    ids = {name: uuid4() for name in ("zoe", "ana", "luis", "cit", "boss", "admin")}
    for name, role in [
        ("zoe", Role.TECNICO),
        ("ana", Role.TECNICO),
        ("luis", Role.GUARDABOSQUES),
        ("cit", Role.CIUDADANO),
        ("boss", Role.AUTORIDAD),
        ("admin", Role.ADMIN),
    ]:
        profiles.roles[ids[name]] = role
        profiles.names[ids[name]] = name.capitalize()
    return ids


def test_use_case_lists_technicians_ordered_by_name(profiles: InMemoryProfileRepository) -> None:
    ids = seed(profiles)
    result = ListUsersByRole(InMemoryUserDirectory(profiles)).execute(Role.TECNICO)
    assert [u.name for u in result] == ["Ana", "Zoe"]
    assert {u.id for u in result} == {ids["ana"], ids["zoe"]}


@pytest.mark.parametrize("role", [Role.CIUDADANO, Role.GUARDABOSQUES, Role.AUTORIDAD, Role.ADMIN])
def test_use_case_refuses_to_enumerate_other_roles(
    profiles: InMemoryProfileRepository, role: Role
) -> None:
    with pytest.raises(DomainValidationError):
        ListUsersByRole(InMemoryUserDirectory(profiles)).execute(role)


@pytest.mark.parametrize("who", ["boss", "admin"])
def test_authority_and_admin_get_only_id_and_name(
    client: TestClient,
    make_token: TokenFactory,
    profiles: InMemoryProfileRepository,
    who: str,
) -> None:
    ids = seed(profiles)
    r = client.get("/api/users?rol=TECNICO", headers=bearer(make_token(ids[who])))
    assert r.status_code == 200, r.text
    body = r.json()
    assert [u["name"] for u in body] == ["Ana", "Zoe"]
    assert all(set(u) == {"id", "name"} for u in body)


@pytest.mark.parametrize("who", ["cit", "luis", "zoe"])
def test_other_roles_are_forbidden(
    client: TestClient,
    make_token: TokenFactory,
    profiles: InMemoryProfileRepository,
    who: str,
) -> None:
    ids = seed(profiles)
    r = client.get("/api/users?rol=TECNICO", headers=bearer(make_token(ids[who])))
    assert r.status_code == 403


def test_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/users?rol=TECNICO").status_code == 401


def test_only_technicians_can_be_listed_and_rol_is_required(
    client: TestClient, make_token: TokenFactory, profiles: InMemoryProfileRepository
) -> None:
    ids = seed(profiles)
    headers = bearer(make_token(ids["boss"]))
    assert client.get("/api/users?rol=CIUDADANO", headers=headers).status_code == 422
    assert client.get("/api/users?rol=NOPE", headers=headers).status_code == 422
    assert client.get("/api/users", headers=headers).status_code == 422
