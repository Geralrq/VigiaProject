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
    provide_profile_repository,
    provide_token_verifier,
    provide_zone_repository,
)
from app.shared.adapters.outbound.auth.jwks_token_verifier import JwksTokenVerifier
from tests.fakes import InMemoryProfileRepository, InMemoryZoneRepository

ISSUER = "https://test-project.supabase.co/auth/v1"
AUDIENCE = "authenticated"
KID = "test-key-1"

TokenFactory = Callable[..., str]


class StaticJWKClient(PyJWKClient):
    """Real PyJWKClient (kid lookup, PyJWK parsing) whose fetch never hits the network."""

    def __init__(self, jwks: dict[str, Any]) -> None:
        super().__init__("https://jwks.invalid/.well-known/jwks.json", cache_keys=True)
        self._jwks = jwks

    def fetch_data(self) -> Any:
        return self._jwks


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
def client(
    verifier: JwksTokenVerifier,
    profiles: InMemoryProfileRepository,
    zones: InMemoryZoneRepository,
) -> TestClient:
    app = create_app()
    app.dependency_overrides[provide_token_verifier] = lambda: verifier
    app.dependency_overrides[provide_profile_repository] = lambda: profiles
    app.dependency_overrides[provide_zone_repository] = lambda: zones
    return TestClient(app)
