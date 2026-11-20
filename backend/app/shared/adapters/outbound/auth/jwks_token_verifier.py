from typing import Any
from uuid import UUID

import jwt
from jwt import PyJWKClient, PyJWKClientConnectionError, PyJWKClientError

from app.shared.domain.errors import AuthenticationError, ServiceUnavailableError
from app.shared.domain.user import VerifiedIdentity

# Only asymmetric algorithms: a symmetric ("oct") key in a public JWKS would let
# anyone holding the public material forge tokens.
ASYMMETRIC_ALGORITHMS = frozenset(
    {"ES256", "ES384", "ES512", "RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "EdDSA"}
)
REQUIRED_CLAIMS = ["exp", "iat", "sub", "aud", "iss"]

INVALID_TOKEN = "El token de acceso no es válido."


def build_jwk_client(jwks_url: str) -> PyJWKClient:
    """JWKS client with the key set cached in-process (refetched on unknown `kid`)."""
    return PyJWKClient(jwks_url, cache_keys=True, cache_jwk_set=True, lifespan=600, timeout=5)


class JwksTokenVerifier:
    """Validates Supabase access tokens against the project's JWKS (PyJWT)."""

    def __init__(
        self, jwk_client: PyJWKClient, *, audience: str, issuer: str, leeway: int = 10
    ) -> None:
        self._jwk_client = jwk_client
        self._audience = audience
        self._issuer = issuer
        self._leeway = leeway

    def verify(self, token: str) -> VerifiedIdentity:
        claims = self._decode(token)
        try:
            subject = UUID(str(claims["sub"]))
        except ValueError as exc:
            raise AuthenticationError(INVALID_TOKEN) from exc
        metadata: dict[str, Any] = claims.get("user_metadata") or {}
        email = claims.get("email")
        name = metadata.get("full_name") or metadata.get("name")
        if not name and email:
            name = email.split("@", 1)[0]
        return VerifiedIdentity(subject=subject, email=email, display_name=name)

    def _decode(self, token: str) -> dict[str, Any]:
        try:
            signing_key = self._jwk_client.get_signing_key_from_jwt(token)
        except PyJWKClientConnectionError as exc:
            raise ServiceUnavailableError(
                "No se pudieron obtener las llaves de autenticación."
            ) from exc
        except (PyJWKClientError, jwt.PyJWTError) as exc:  # unknown kid, malformed token
            raise AuthenticationError(INVALID_TOKEN) from exc

        algorithm = signing_key.algorithm_name  # taken from the key, never from the token
        if algorithm not in ASYMMETRIC_ALGORITHMS:
            raise AuthenticationError(INVALID_TOKEN)
        try:
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=[algorithm],
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._leeway,
                options={"require": REQUIRED_CLAIMS},
            )
        except jwt.ExpiredSignatureError as exc:
            raise AuthenticationError("El token de acceso expiró.") from exc
        except jwt.PyJWTError as exc:
            raise AuthenticationError(INVALID_TOKEN) from exc
