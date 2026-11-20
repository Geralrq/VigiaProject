"""Telegram: signed link codes, webhook, /me endpoints and the httpx adapter (MockTransport)."""

import base64
import json
import logging
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.notifications.adapters.outbound.telegram_adapter import TelegramAdapter
from app.notifications.application.use_cases.telegram_linking import (
    HandleTelegramMessage,
    SetTelegramChat,
    TelegramMessageIn,
    WebhookOutcome,
)
from app.notifications.domain.link_code import LinkCodeSigner
from app.notifications.domain.notice import AlertNotice, NotificationDeliveryError
from app.shared.domain.errors import (
    AuthorizationError,
    DomainValidationError,
    ServiceUnavailableError,
)
from app.shared.domain.events import Recipient
from tests.conftest import BOT_USERNAME, LINK_SECRET, WEBHOOK_SECRET, TokenFactory
from tests.fakes_alerts import FakeTelegramChat, InMemoryChatLinkRepository
from tests.test_scan_api import bearer

SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"


class Clock:
    def __init__(self, now: float = 1_800_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


# --- signed link code -------------------------------------------------------------------------


def test_link_code_round_trips_and_fits_a_telegram_start_payload() -> None:
    signer = LinkCodeSigner(LINK_SECRET)
    user = uuid4()
    code = signer.issue(user)
    assert signer.verify(code.value) == user
    assert len(code.value) <= 64 and code.value.replace("-", "").replace("_", "").isalnum()


def test_link_code_expires() -> None:
    clock = Clock()
    signer = LinkCodeSigner(LINK_SECRET, ttl_seconds=600, clock=clock)
    code = signer.issue(uuid4()).value

    clock.now += 600
    signer.verify(code)  # still valid at the deadline
    clock.now += 1
    with pytest.raises(DomainValidationError, match="expiró"):
        signer.verify(code)


def test_link_code_rejects_tampering_other_keys_and_garbage() -> None:
    signer = LinkCodeSigner(LINK_SECRET)
    user, victim = uuid4(), uuid4()
    code = signer.issue(user).value

    raw = bytearray(base64.urlsafe_b64decode(code + "=="))
    raw[:16] = victim.bytes  # swap the user, keep the signature
    forged = base64.urlsafe_b64encode(bytes(raw)).rstrip(b"=").decode()

    other_key = LinkCodeSigner("another-secret").issue(user).value
    for bad in (forged, other_key, "", "abc", "!!!!", code[:-2], code + "AA"):
        with pytest.raises(DomainValidationError):
            signer.verify(bad)


def test_link_code_needs_a_configured_secret() -> None:
    with pytest.raises(ServiceUnavailableError):
        LinkCodeSigner("").issue(uuid4())
    with pytest.raises(ServiceUnavailableError):
        LinkCodeSigner("").verify("anything")


# --- webhook use case -------------------------------------------------------------------------


def handler(
    clock: Clock | None = None, *, known: set[UUID] | None = None, chat_fails: bool = False
) -> tuple[HandleTelegramMessage, LinkCodeSigner, InMemoryChatLinkRepository, FakeTelegramChat]:
    signer = LinkCodeSigner(LINK_SECRET, clock=clock or Clock())
    links = InMemoryChatLinkRepository(known)
    chat = FakeTelegramChat(fails=chat_fails)
    return HandleTelegramMessage(signer, links, chat), signer, links, chat


def test_start_with_a_valid_code_links_the_chat() -> None:
    use_case, signer, links, chat = handler()
    user = uuid4()

    outcome = use_case.execute(
        TelegramMessageIn(900, f"/start {signer.issue(user).value}", "private")
    )

    assert outcome is WebhookOutcome.LINKED
    assert links.chats == {user: 900}
    assert chat.sent and chat.sent[0][0] == 900 and "alertas" in chat.sent[0][1]


def test_start_with_an_expired_code_does_not_link() -> None:
    clock = Clock()
    use_case, signer, links, chat = handler(clock)
    code = signer.issue(uuid4()).value

    clock.now += 601
    outcome = use_case.execute(TelegramMessageIn(900, f"/start {code}"))

    assert outcome is WebhookOutcome.INVALID_CODE
    assert links.chats == {}
    assert "expiró" in chat.sent[0][1]


@pytest.mark.parametrize("text", ["/start nope", "/start", "/start    "])
def test_start_with_a_bad_or_missing_code_does_not_link(text: str) -> None:
    use_case, _, links, chat = handler()
    outcome = use_case.execute(TelegramMessageIn(900, text))
    assert outcome in (WebhookOutcome.INVALID_CODE, WebhookOutcome.MISSING_CODE)
    assert links.chats == {} and len(chat.sent) == 1


@pytest.mark.parametrize(
    ("text", "chat_type"),
    [("hola", "private"), (None, "private"), ("/help", None), ("/startx abc", None)],
)
def test_other_messages_are_ignored(text: str | None, chat_type: str | None) -> None:
    use_case, _, links, chat = handler()
    assert use_case.execute(TelegramMessageIn(900, text, chat_type)) is WebhookOutcome.IGNORED
    assert links.chats == {} and chat.sent == []


def test_a_group_chat_is_never_linked() -> None:
    use_case, signer, links, _ = handler()
    message = TelegramMessageIn(-100, f"/start {signer.issue(uuid4()).value}", "supergroup")
    assert use_case.execute(message) is WebhookOutcome.IGNORED
    assert links.chats == {}


def test_start_accepts_the_bot_suffix() -> None:
    use_case, signer, links, _ = handler()
    user = uuid4()
    code = signer.issue(user).value
    assert (
        use_case.execute(TelegramMessageIn(5, f"/start@VigiaBot {code}")) is WebhookOutcome.LINKED
    )
    assert links.chats[user] == 5


def test_a_chat_already_linked_to_someone_else_is_refused() -> None:
    use_case, signer, links, chat = handler()
    links.chats[uuid4()] = 900
    outcome = use_case.execute(TelegramMessageIn(900, f"/start {signer.issue(uuid4()).value}"))
    assert outcome is WebhookOutcome.CHAT_TAKEN
    assert "otra cuenta" in chat.sent[0][1]


def test_a_failing_reply_does_not_break_the_linking() -> None:
    use_case, signer, links, _ = handler(chat_fails=True)
    user = uuid4()
    outcome = use_case.execute(TelegramMessageIn(900, f"/start {signer.issue(user).value}"))
    assert outcome is WebhookOutcome.LINKED and links.chats == {user: 900}


def test_code_for_a_missing_profile_is_reported_not_crashed() -> None:
    use_case, signer, _, _ = handler(known=set())
    outcome = use_case.execute(TelegramMessageIn(900, f"/start {signer.issue(uuid4()).value}"))
    assert outcome is WebhookOutcome.INVALID_CODE


# --- webhook endpoint -------------------------------------------------------------------------


def update(text: str, chat_id: int = 900) -> dict[str, object]:
    return {
        "update_id": 1,
        "message": {"message_id": 7, "text": text, "chat": {"id": chat_id, "type": "private"}},
    }


def test_webhook_with_the_valid_secret_links_the_chat(
    client: TestClient,
    link_signer: LinkCodeSigner,
    chat_links: InMemoryChatLinkRepository,
    telegram_chat: FakeTelegramChat,
) -> None:
    user = uuid4()
    r = client.post(
        "/api/telegram/webhook",
        json=update(f"/start {link_signer.issue(user).value}"),
        headers={SECRET_HEADER: WEBHOOK_SECRET},
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True, "result": "linked"}
    assert chat_links.chats == {user: 900}
    assert telegram_chat.sent[0][0] == 900


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {SECRET_HEADER: ""},
        {SECRET_HEADER: WEBHOOK_SECRET + "x"},
        {SECRET_HEADER: WEBHOOK_SECRET[:-1]},
        {SECRET_HEADER: "wrong"},
        {"Authorization": f"Bearer {WEBHOOK_SECRET}"},
    ],
    ids=["missing", "empty", "suffix", "prefix", "wrong", "wrong-header"],
)
def test_webhook_with_an_invalid_secret_is_401_and_changes_nothing(
    client: TestClient,
    link_signer: LinkCodeSigner,
    chat_links: InMemoryChatLinkRepository,
    telegram_chat: FakeTelegramChat,
    headers: dict[str, str],
) -> None:
    user = uuid4()
    r = client.post(
        "/api/telegram/webhook",
        json=update(f"/start {link_signer.issue(user).value}"),
        headers=headers,
    )
    assert r.status_code == 401
    assert r.headers["content-type"] == "application/problem+json"
    assert chat_links.chats == {} and telegram_chat.sent == []


def test_webhook_is_refused_when_no_secret_is_configured(client: TestClient) -> None:
    from app.bootstrap import provide_telegram_webhook_secret

    client.app.dependency_overrides[provide_telegram_webhook_secret] = lambda: ""  # type: ignore[attr-defined]
    r = client.post("/api/telegram/webhook", json=update("/start x"), headers={SECRET_HEADER: ""})
    assert r.status_code == 503


def test_webhook_with_an_expired_code_answers_200_and_does_not_link(
    client: TestClient,
    chat_links: InMemoryChatLinkRepository,
    telegram_chat: FakeTelegramChat,
) -> None:
    from app.bootstrap import provide_link_code_signer

    clock = Clock()
    signer = LinkCodeSigner(LINK_SECRET, clock=clock)
    code = signer.issue(uuid4()).value
    clock.now += 3600
    client.app.dependency_overrides[provide_link_code_signer] = lambda: signer  # type: ignore[attr-defined]

    r = client.post(
        "/api/telegram/webhook",
        json=update(f"/start {code}"),
        headers={SECRET_HEADER: WEBHOOK_SECRET},
    )

    assert r.status_code == 200  # Telegram must not retry
    assert r.json()["result"] == "invalid_code"
    assert chat_links.chats == {}
    assert "expiró" in telegram_chat.sent[0][1]


@pytest.mark.parametrize(
    "body",
    [
        {"update_id": 2},
        {"update_id": 3, "edited_message": {"text": "x"}},
        {"message": {"chat": {"id": 1}}},
    ],
    ids=["empty", "other-update-kind", "no-text"],
)
def test_webhook_acknowledges_updates_it_does_not_handle(
    client: TestClient, body: dict[str, object]
) -> None:
    r = client.post("/api/telegram/webhook", json=body, headers={SECRET_HEADER: WEBHOOK_SECRET})
    assert r.status_code == 200 and r.json()["result"] == "ignored"


# --- /api/me/telegram-link and /api/me/telegram -----------------------------------------------


def test_telegram_link_endpoint_issues_a_code_for_the_caller(
    client: TestClient, make_token: TokenFactory, link_signer: LinkCodeSigner
) -> None:
    user = uuid4()
    assert client.get("/api/me/telegram-link").status_code == 401

    r = client.get("/api/me/telegram-link", headers=bearer(make_token(user)))

    assert r.status_code == 200
    body = r.json()
    assert link_signer.verify(body["code"]) == user
    assert body["command"] == f"/start {body['code']}"
    assert body["deep_link"] == f"https://t.me/{BOT_USERNAME}?start={body['code']}"


def test_patch_me_telegram_links_the_callers_chat(
    client: TestClient, make_token: TokenFactory, chat_links: InMemoryChatLinkRepository
) -> None:
    user = uuid4()
    assert client.patch("/api/me/telegram", json={"chat_id": 5}).status_code == 401

    r = client.patch("/api/me/telegram", json={"chat_id": 4242}, headers=bearer(make_token(user)))

    assert r.status_code == 200 and r.json() == {"chat_id": 4242}
    assert chat_links.chats == {user: 4242}


def test_patch_me_telegram_conflict_and_validation(
    client: TestClient, make_token: TokenFactory, chat_links: InMemoryChatLinkRepository
) -> None:
    chat_links.chats[uuid4()] = 4242
    taken = client.patch("/api/me/telegram", json={"chat_id": 4242}, headers=bearer(make_token()))
    assert taken.status_code == 409
    assert taken.headers["content-type"] == "application/problem+json"
    for body in ({"chat_id": "abc"}, {}, {"chat_id": 1, "extra": 1}):
        r = client.patch("/api/me/telegram", json=body, headers=bearer(make_token()))
        assert r.status_code == 422


def test_manual_linking_is_refused_outside_demo_mode() -> None:
    links = InMemoryChatLinkRepository()
    with pytest.raises(AuthorizationError):
        SetTelegramChat(links, allow_manual=False).execute(uuid4(), 1)
    assert links.chats == {}


# --- TelegramAdapter (httpx MockTransport) ----------------------------------------------------

TOKEN = "123456:SECRET-BOT-TOKEN"
NOTICE = AlertNotice(UUID(int=7), "ALTO", "Paramillo", "INCENDIO", 38.0)


def adapter(handler_fn, token: str = TOKEN) -> TelegramAdapter:
    return TelegramAdapter(
        token, "https://vigia.example", transport=httpx.MockTransport(handler_fn)
    )


def test_adapter_posts_send_message_with_the_spanish_text() -> None:
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    adapter(respond).send(Recipient(uuid4(), 321), NOTICE)

    [request] = seen
    assert request.url.path == f"/bot{TOKEN}/sendMessage"
    body = json.loads(request.content)
    assert body["chat_id"] == 321
    assert "ALTO" in body["text"] and "Paramillo" in body["text"] and "38.0 ha" in body["text"]
    assert f"https://vigia.example/a/{NOTICE.alert_id}" in body["text"]


def test_adapter_skips_recipients_without_a_linked_chat() -> None:
    adapter(lambda r: pytest.fail("no request expected")).send(Recipient(uuid4(), None), NOTICE)


def test_adapter_without_token_only_logs(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        adapter(lambda r: pytest.fail("no request expected"), token="").send(
            Recipient(uuid4(), 321), NOTICE
        )
    assert "telegram simulado" in caplog.text and "Paramillo" in caplog.text


@pytest.mark.parametrize("failure", ["status", "transport"])
def test_adapter_failures_are_reported_without_leaking_the_token(
    failure: str, caplog: pytest.LogCaptureFixture
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if failure == "transport":
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(401, json={"ok": False})

    with pytest.raises(NotificationDeliveryError) as info:
        adapter(respond).send(Recipient(uuid4(), 321), NOTICE)

    assert "SECRET-BOT-TOKEN" not in str(info.value)
    # the original httpx error (whose message carries the URL, hence the token) is dropped
    assert info.value.__cause__ is None
    assert info.value.__context__ is None or info.value.__suppress_context__
