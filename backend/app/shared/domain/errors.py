class DomainError(Exception):
    """Base error. The inbound layer maps each subclass to a problem+json status."""

    def __init__(self, detail: str = "") -> None:
        super().__init__(detail)
        self.detail = detail


class AuthenticationError(DomainError):
    """Missing, malformed, expired or otherwise invalid credentials."""


class AuthorizationError(DomainError):
    """Authenticated, but the user's role does not allow the action."""


class NotFoundError(DomainError):
    pass


class DomainValidationError(DomainError):
    """A domain invariant was violated by the input."""


class ServiceUnavailableError(DomainError):
    """A required external dependency (e.g. the JWKS endpoint) is unreachable."""
