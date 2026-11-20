from uuid import uuid4

import pytest

from app.shared.application.use_cases.authenticate_user import AuthenticateUser
from app.shared.domain.errors import AuthorizationError
from app.shared.domain.user import Role, User, VerifiedIdentity
from tests.fakes import InMemoryProfileRepository


class StubVerifier:
    def __init__(self, identity: VerifiedIdentity) -> None:
        self.identity = identity

    def verify(self, token: str) -> VerifiedIdentity:
        return self.identity


def test_first_sign_in_creates_citizen_profile() -> None:
    sub = uuid4()
    profiles = InMemoryProfileRepository()
    use_case = AuthenticateUser(StubVerifier(VerifiedIdentity(sub, display_name="Ana")), profiles)

    user = use_case.execute("token")

    assert user == User(id=sub, role=Role.CIUDADANO)
    assert profiles.roles[sub] is Role.CIUDADANO
    assert profiles.names[sub] == "Ana"


def test_existing_profile_role_is_used() -> None:
    sub = uuid4()
    profiles = InMemoryProfileRepository({sub: Role.TECNICO})
    user = AuthenticateUser(StubVerifier(VerifiedIdentity(sub)), profiles).execute("token")
    assert user.role is Role.TECNICO


def test_missing_name_falls_back_to_default() -> None:
    sub = uuid4()
    profiles = InMemoryProfileRepository()
    AuthenticateUser(StubVerifier(VerifiedIdentity(sub)), profiles).execute("token")
    assert profiles.names[sub] == "Usuario"


def test_ensure_any_role() -> None:
    User(uuid4(), Role.ADMIN).ensure_any_role([Role.ADMIN])
    with pytest.raises(AuthorizationError):
        User(uuid4(), Role.CIUDADANO).ensure_any_role([Role.ADMIN, Role.AUTORIDAD])
