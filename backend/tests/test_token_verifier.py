from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from app.shared.adapters.outbound.auth.jwks_token_verifier import JwksTokenVerifier
from app.shared.domain.errors import AuthenticationError
from tests.conftest import TokenFactory


def test_valid_token_yields_identity(verifier: JwksTokenVerifier, make_token: TokenFactory) -> None:
    sub = uuid4()
    identity = verifier.verify(make_token(sub))
    assert identity.subject == sub
    assert identity.email == "ana@example.org"
    assert identity.display_name == "Ana Pérez"


def test_expired_token_is_rejected(verifier: JwksTokenVerifier, make_token: TokenFactory) -> None:
    with pytest.raises(AuthenticationError, match="expiró"):
        verifier.verify(make_token(expires_in=-120))  # beyond the 10 s leeway


def test_wrong_audience_is_rejected(verifier: JwksTokenVerifier, make_token: TokenFactory) -> None:
    with pytest.raises(AuthenticationError):
        verifier.verify(make_token(aud="anon"))


def test_wrong_issuer_is_rejected(verifier: JwksTokenVerifier, make_token: TokenFactory) -> None:
    with pytest.raises(AuthenticationError):
        verifier.verify(make_token(iss="https://evil.example/auth/v1"))


def test_invalid_signature_is_rejected(
    verifier: JwksTokenVerifier, make_token: TokenFactory
) -> None:
    attacker_key = ec.generate_private_key(ec.SECP256R1())
    with pytest.raises(AuthenticationError):
        verifier.verify(make_token(key=attacker_key))  # same kid, different key


def test_unknown_kid_is_rejected(verifier: JwksTokenVerifier, make_token: TokenFactory) -> None:
    with pytest.raises(AuthenticationError):
        verifier.verify(make_token(kid="rotated-away"))


def test_malformed_token_is_rejected(verifier: JwksTokenVerifier) -> None:
    with pytest.raises(AuthenticationError):
        verifier.verify("not-a-jwt")


def test_non_uuid_subject_is_rejected(
    verifier: JwksTokenVerifier, make_token: TokenFactory
) -> None:
    with pytest.raises(AuthenticationError):
        verifier.verify(make_token(sub="service-account"))
