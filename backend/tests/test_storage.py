"""Storage adapters: Supabase Storage over httpx (MockTransport) and the in-memory demo one."""

import json

import httpx
import pytest

from app.shared.adapters.outbound.storage.in_memory_storage import InMemoryStorage
from app.shared.adapters.outbound.storage.supabase_storage import SupabaseStorageAdapter
from app.shared.domain.errors import ConflictError, ServiceUnavailableError

URL = "https://proj.supabase.co"
KEY = "service-key-SECRET"


def adapter(handler, key: str = KEY, url: str = URL) -> SupabaseStorageAdapter:
    return SupabaseStorageAdapter(url, key, "evidencias", transport=httpx.MockTransport(handler))


def test_upload_posts_the_bytes_to_the_private_bucket_without_overwriting() -> None:
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"Key": "evidencias/misiones/a.png"})

    adapter(respond).upload("misiones/a.png", b"PNGDATA", "image/png")

    [request] = seen
    assert request.method == "POST"
    assert str(request.url) == f"{URL}/storage/v1/object/evidencias/misiones/a.png"
    assert request.content == b"PNGDATA"
    assert request.headers["content-type"] == "image/png"
    assert request.headers["x-upsert"] == "false"
    assert request.headers["apikey"] == KEY and request.headers["authorization"] == f"Bearer {KEY}"


def test_new_style_secret_keys_are_sent_as_apikey_only() -> None:
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={})

    adapter(respond, key="sb_secret_abc").upload("a.png", b"x", "image/png")
    assert seen[0].headers["apikey"] == "sb_secret_abc"
    assert "authorization" not in seen[0].headers


@pytest.mark.parametrize("failure", ["status", "transport"])
def test_upload_failures_are_503_and_never_leak_the_key(
    failure: str, caplog: pytest.LogCaptureFixture
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if failure == "transport":
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(400, json={"message": "bucket not found"})

    with caplog.at_level("ERROR"), pytest.raises(ServiceUnavailableError) as info:
        adapter(respond).upload("a.png", b"x", "image/png")

    assert KEY not in str(info.value) and KEY not in caplog.text
    assert info.value.__cause__ is None


def test_signed_urls_use_one_batch_call_with_a_one_hour_expiry() -> None:
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json=[
                {
                    "path": "a/1.png",
                    "signedURL": "/object/sign/evidencias/a/1.png?token=T1",
                    "error": None,
                },
                {"path": "a/2.png", "signedURL": None, "error": "Object not found"},
            ],
        )

    urls = adapter(respond).signed_urls(["a/1.png", "a/2.png", "a/1.png"])

    [request] = seen
    assert str(request.url) == f"{URL}/storage/v1/object/sign/evidencias"
    assert json.loads(request.content) == {"expiresIn": 3600, "paths": ["a/1.png", "a/2.png"]}
    assert urls == {
        "a/1.png": f"{URL}/storage/v1/object/sign/evidencias/a/1.png?token=T1",
        "a/2.png": None,
    }


def test_signing_failure_degrades_to_no_url_instead_of_failing_the_request() -> None:
    urls = adapter(lambda r: httpx.Response(500)).signed_urls(["a.png"])
    assert urls == {"a.png": None}
    assert adapter(lambda r: pytest.fail("no call expected")).signed_urls([]) == {}


def test_without_credentials_every_call_is_unavailable() -> None:
    unconfigured = adapter(lambda r: pytest.fail("no call expected"), key="", url="")
    with pytest.raises(ServiceUnavailableError, match="no está configurado"):
        unconfigured.upload("a.png", b"x", "image/png")
    assert unconfigured.signed_urls(["a.png"]) == {"a.png": None}


def test_in_memory_storage_returns_marker_urls_and_never_overwrites() -> None:
    storage = InMemoryStorage()
    storage.upload("misiones/a.png", b"x", "image/png")
    assert storage.objects["misiones/a.png"] == (b"x", "image/png")
    [url] = storage.signed_urls(["misiones/a.png"]).values()
    assert url and url.startswith("https://storage.demo.invalid/evidencias/misiones/a.png")
    with pytest.raises(ConflictError):
        storage.upload("misiones/a.png", b"y", "image/png")


def test_download_returns_the_object_bytes_with_the_service_key() -> None:
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"PDFBYTES")

    assert adapter(respond).download("informes/a b.pdf") == b"PDFBYTES"
    assert str(seen[0].url) == f"{URL}/storage/v1/object/evidencias/informes/a%20b.pdf"
    assert seen[0].headers["apikey"] == KEY


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(404, json={"error": "not_found"}),
        httpx.Response(
            400,
            json={"statusCode": "404", "error": "Bucket not found", "message": "Object not found"},
        ),
    ],
    ids=["404", "400-not-found"],
)
def test_download_of_a_missing_object_is_not_found(response: httpx.Response) -> None:
    from app.shared.domain.errors import NotFoundError

    with pytest.raises(NotFoundError):
        adapter(lambda r: response).download("x.pdf")


def test_download_failures_are_503_and_never_leak_the_key(caplog: pytest.LogCaptureFixture) -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    with caplog.at_level("ERROR"), pytest.raises(ServiceUnavailableError):
        adapter(boom).download("x.pdf")
    with pytest.raises(ServiceUnavailableError):
        adapter(lambda r: httpx.Response(500)).download("x.pdf")
    with pytest.raises(ServiceUnavailableError, match="no está configurado"):
        adapter(lambda r: pytest.fail("no call"), key="", url="").download("x.pdf")
    assert KEY not in caplog.text


def test_upload_overwrite_sets_the_upsert_header() -> None:
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={})

    adapter(respond).upload("a.pdf", b"x", "application/pdf", overwrite=True)
    adapter(respond).upload("a.pdf", b"x", "application/pdf")
    assert [r.headers["x-upsert"] for r in seen] == ["true", "false"]


def test_in_memory_download_and_overwrite() -> None:
    from app.shared.domain.errors import NotFoundError

    storage = InMemoryStorage()
    storage.upload("a.pdf", b"v1", "application/pdf")
    storage.upload("a.pdf", b"v2", "application/pdf", overwrite=True)
    assert storage.download("a.pdf") == b"v2"
    with pytest.raises(NotFoundError):
        storage.download("missing.pdf")
