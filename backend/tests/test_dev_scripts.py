"""Dev scripts: reset_demo refuses live; create_dev_users is idempotent. Fakes, no network/DB."""

from uuid import UUID, uuid4

import pytest

from app.shared.adapters.outbound.storage.in_memory_storage import InMemoryStorage
from scripts.create_dev_users import DEV_USERS, DevUsersError, create_dev_users
from scripts.reset_demo import SEED_THRESHOLDS, ResetRefused, delete_storage, reset_demo

PASSWORD = "s3cret-dev-password"


class FakeAuth:
    def __init__(self) -> None:
        self.users: dict[str, UUID] = {}
        self.created: list[str] = []

    def find_user_id(self, email: str) -> UUID | None:
        return self.users.get(email)

    def create_user(self, email: str, password: str) -> UUID:
        assert password == PASSWORD
        self.users[email] = uuid4()
        self.created.append(email)
        return self.users[email]


class FakeProfiles:
    def __init__(self) -> None:
        self.rows: dict[UUID, tuple[str, str, tuple[float, float] | None]] = {}

    def upsert(self, user_id, nombre, rol, location) -> None:
        self.rows[user_id] = (nombre, rol, location)


def test_create_dev_users_is_idempotent(capsys) -> None:
    auth, profiles = FakeAuth(), FakeProfiles()

    first = create_dev_users(auth, profiles, PASSWORD, app_mode="demo")
    second = create_dev_users(auth, profiles, PASSWORD, app_mode="demo")

    assert [r.created for r in first] == [True] * 5
    assert [r.created for r in second] == [False] * 5
    assert len(auth.created) == 5 and len(profiles.rows) == 5  # nothing duplicated
    assert {r.email: r.role for r in first} == {e: rol for e, _n, rol, _l in DEV_USERS}
    assert {rol for _n, rol, _l in profiles.rows.values()} == {
        "CIUDADANO",
        "GUARDABOSQUES",
        "TECNICO",
        "AUTORIDAD",
        "ADMIN",
    }
    located = {rol for _n, rol, loc in profiles.rows.values() if loc}
    assert located == {"CIUDADANO", "GUARDABOSQUES"}
    assert PASSWORD not in capsys.readouterr().out


@pytest.mark.parametrize("mode", ["live", ""])
def test_create_dev_users_only_runs_in_demo(mode) -> None:
    auth = FakeAuth()
    with pytest.raises(DevUsersError):
        create_dev_users(auth, FakeProfiles(), PASSWORD, app_mode=mode)
    assert auth.users == {}


def test_create_dev_users_needs_a_password() -> None:
    with pytest.raises(DevUsersError):
        create_dev_users(FakeAuth(), FakeProfiles(), "", app_mode="demo")


class FakeStore:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def storage_paths(self) -> list[str]:
        self.calls.append("paths")
        return ["anomalias/a/antes.png", "informes/i.pdf"]

    def delete_scenario(self) -> dict[str, int]:
        self.calls.append("delete")
        return {"anomalies": 2, "alerts": 1}

    def restore_thresholds(self, seed: dict) -> int:
        self.calls.append("thresholds")
        assert seed == SEED_THRESHOLDS and len(seed) == 3
        return len(seed)

    def zero_points(self) -> int:
        self.calls.append("points")
        return 6


def test_reset_demo_refuses_live() -> None:
    store = FakeStore()
    with pytest.raises(ResetRefused):
        reset_demo(store, app_mode="live")
    assert store.calls == []  # touched nothing


def test_reset_demo_in_demo_resets_everything_and_cleans_storage() -> None:
    store, storage = FakeStore(), InMemoryStorage()
    for path in ("anomalias/a/antes.png", "informes/i.pdf", "otro/queda.png"):
        storage.upload(path, b"x", "image/png")

    summary = reset_demo(store, app_mode="demo")
    delete_storage(storage, summary)

    assert store.calls == ["paths", "delete", "thresholds", "points"]  # paths read before delete
    assert summary.deleted == {"anomalies": 2, "alerts": 1}
    assert (summary.zones_restored, summary.profiles_zeroed) == (3, 6)
    assert set(storage.objects) == {"otro/queda.png"}
    assert summary.storage_deleted == 2 and summary.storage_failed == []
