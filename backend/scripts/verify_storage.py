"""Phase 6b check of the REAL Supabase Storage with the service key from .env.local.

Run from /backend:  uv run python -m scripts.verify_storage

Uploads a minimal PNG to the private bucket `evidencias`, asks for its signed URL,
downloads it with httpx and compares the bytes, checks that the object is NOT readable
without the signature, and deletes it. The key and the signed URL (which carries a token)
are never printed; only step results are.
"""

import base64
import json
import sys
from uuid import uuid4

import httpx

from app.bootstrap import EVIDENCE_BUCKET
from app.shared.adapters.outbound.storage.supabase_storage import SupabaseStorageAdapter
from app.shared.domain.errors import DomainError, NotFoundError
from app.shared.settings import get_settings

# 1x1 transparent PNG
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGD4DwABBAEAHbE9nQAAAABJRU5ErkJggg=="
)


def key_kind(key: str) -> str:
    """What kind of key this is, from its public shape only (never the key itself)."""
    if key.startswith("sb_"):
        return "_".join(key.split("_")[:2])  # sb_secret | sb_publishable
    if key.count(".") == 2:  # legacy JWT keys carry their role in the (non-secret) payload
        payload = key.split(".")[1]
        try:
            claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
            return f"jwt:{claims.get('role', '?')}"
        except ValueError:
            return "jwt:unreadable"
    return "unknown"


def step(ok: bool, label: str) -> None:
    print(f"[{'ok' if ok else 'FAIL'}] {label}")
    if not ok:
        raise SystemExit(1)


def main() -> None:
    settings = get_settings()
    key = settings.supabase_service_key.get_secret_value()
    if not (key and settings.supabase_url):
        print("[skip] SUPABASE_URL / SUPABASE_SERVICE_KEY are not configured in .env.local")
        sys.exit(2)
    kind = key_kind(key)
    print(f"service key configured: yes (not printed) | kind: {kind} | bucket: {EVIDENCE_BUCKET}")
    if kind in ("sb_publishable", "jwt:anon"):
        print(
            "[FAIL] that is a PUBLIC key (the one the browser uses): Storage treats it as anonymous\n"
            "       and refuses the upload. Put the server key in .env.local as SUPABASE_SERVICE_KEY:\n"
            "       the 'secret' key (sb_secret_...) or the legacy service_role key, from\n"
            "       Project Settings > API Keys. Never use it in the frontend."
        )
        sys.exit(1)

    storage = SupabaseStorageAdapter(settings.supabase_url, key, EVIDENCE_BUCKET)
    path = f"verificacion/{uuid4()}.png"
    try:
        storage.upload(path, PNG, "image/png")
        step(True, f"upload {path} ({len(PNG)} bytes)")

        signed = storage.signed_urls([path])[path]
        step(
            signed is not None and "token=" in signed, "signed URL issued (1 hour; URL not printed)"
        )
        assert signed is not None

        downloaded = httpx.get(signed, timeout=30)
        step(downloaded.status_code == 200, f"signed URL download -> HTTP {downloaded.status_code}")
        step(downloaded.content == PNG, "downloaded bytes identical to the uploaded PNG")
        step(
            downloaded.headers.get("content-type", "").startswith("image/png"),
            f"content-type {downloaded.headers.get('content-type')}",
        )

        unsigned = signed.split("?", 1)[0]
        denied = httpx.get(unsigned, timeout=30)
        step(
            denied.status_code >= 400,
            f"same object WITHOUT the token -> HTTP {denied.status_code} (private)",
        )
        public = httpx.get(
            f"{settings.supabase_url.rstrip('/')}/storage/v1/object/public/{EVIDENCE_BUCKET}/{path}",
            timeout=30,
        )
        step(
            public.status_code >= 400,
            f"public URL -> HTTP {public.status_code} (bucket is not public)",
        )

        step(
            storage.download(path) == PNG,
            "download() through the service key returns the same bytes",
        )
        replacement = PNG + b"\0"
        storage.upload(path, replacement, "image/png", overwrite=True)
        step(
            storage.download(path) == replacement,
            "upload(overwrite=True) replaces the object (used for PDFs)",
        )
        try:
            storage.download(f"verificacion/{uuid4()}-no-existe.png")
        except NotFoundError:
            step(True, "download() of a missing object -> NotFoundError")
        else:
            step(False, "download() of a missing object did not fail")

        pdf_path = f"verificacion/{uuid4()}.pdf"
        try:
            storage.upload(pdf_path, b"%PDF-1.4\n%%EOF\n", "application/pdf", overwrite=True)
            step(True, "the bucket accepts application/pdf (inspection reports)")
        finally:
            storage.delete([pdf_path])

        try:  # the adapter refuses to overwrite
            storage.upload(path, b"x", "image/png")
        except DomainError:
            step(True, "second upload to the same path refused (no overwrite)")
        else:
            step(False, "second upload to the same path was accepted")
    finally:
        try:
            storage.delete([path])
            gone = storage.signed_urls([path]).get(path)
            check = httpx.get(gone, timeout=30).status_code if gone else 404
            step(check >= 400, f"object deleted (signed URL now -> HTTP {check})")
        except DomainError as exc:
            print(f"[FAIL] cleanup: {exc.detail}")
            raise SystemExit(1) from None
    print("OK")


if __name__ == "__main__":
    main()
