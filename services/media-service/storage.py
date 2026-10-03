"""Image upload storage: S3 in production, local disk when S3 isn't reachable
(no credentials, bucket missing, etc.) -- ported from the original
monolith's storage.py essentially unchanged, now returning the backend used
and byte size too so media-service can record them in its asset registry.
"""
from __future__ import annotations

import io
import os
import uuid
from pathlib import Path
from typing import BinaryIO

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from werkzeug.utils import secure_filename

from metrics import S3_FALLBACK_TOTAL, UPLOAD_DURATION

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # 8 MB
LOCAL_UPLOAD_DIR = Path(__file__).resolve().parent / "static" / "uploads"


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _unique_name(original_filename: str) -> str:
    ext = secure_filename(original_filename).rsplit(".", 1)[-1].lower()
    return f"{uuid.uuid4().hex}.{ext}"


def save_image(file_obj: BinaryIO, original_filename: str) -> tuple[str, str, int]:
    """Returns (url, backend, size_bytes). Raises ValueError for invalid
    input (a user error, not an infrastructure failure)."""
    if not original_filename or not allowed_file(original_filename):
        raise ValueError(f"Unsupported file type: {original_filename!r}")

    key = _unique_name(original_filename)
    bucket_name = os.getenv("S3_BUCKET_NAME", "darviq-social-media-assets")

    # Read into memory once: boto3's upload_fileobj closes whatever file
    # object it's given as part of its own cleanup, even on failure, so the
    # original stream can't be safely re-read afterward for the local
    # fallback.
    data = file_obj.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(f"File too large: {len(data)} bytes (max {MAX_UPLOAD_BYTES})")

    with UPLOAD_DURATION.labels(backend="s3").time():
        try:
            s3_client = boto3.client("s3")
            s3_client.upload_fileobj(io.BytesIO(data), bucket_name, key)
            region = s3_client.meta.region_name or "us-east-1"
            return f"https://{bucket_name}.s3.{region}.amazonaws.com/{key}", "s3", len(data)
        except (BotoCoreError, ClientError):
            S3_FALLBACK_TOTAL.inc()

    with UPLOAD_DURATION.labels(backend="local").time():
        LOCAL_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        dest = LOCAL_UPLOAD_DIR / key
        dest.write_bytes(data)
        # Under "/api/media" (not "/static") so this resolves through the
        # gateway from the browser -- media-service itself is never
        # reachable directly, only the gateway is (see k8s/network-policies.yaml).
        # The "/api" prefix specifically matches the gateway's fixed
        # strip-only-"/api" proxy rule (services/gateway/app.py) -- every
        # browser-facing URL this app hands out needs it.
        return f"/api/media/uploads/{key}", "local", len(data)
