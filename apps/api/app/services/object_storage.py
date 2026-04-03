from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from app.core.config import get_settings
from app.services.provider_health import (
    close_provider_circuit,
    get_open_circuit_reason,
    open_provider_circuit,
)

settings = get_settings()

OBJECT_STORAGE_PROVIDER_NAME = "object-storage"


@dataclass
class StorageUploadResult:
    bucket: str | None = None
    object_key: str | None = None
    url: str | None = None
    expires_at: str | None = None
    etag: str | None = None
    fallback_reason: str | None = None


def is_object_storage_configured() -> bool:
    return bool(
        settings.storage_s3_endpoint_url
        and settings.storage_s3_bucket_name
        and settings.storage_s3_access_key_id
        and settings.storage_s3_secret_access_key
    )


@lru_cache
def _get_s3_client():
    import boto3
    from botocore.config import Config as BotoConfig

    session = boto3.session.Session()
    return session.client(
        "s3",
        endpoint_url=settings.storage_s3_endpoint_url,
        aws_access_key_id=settings.storage_s3_access_key_id,
        aws_secret_access_key=settings.storage_s3_secret_access_key,
        region_name=settings.storage_s3_region,
        config=BotoConfig(
            signature_version="s3v4",
            connect_timeout=settings.storage_s3_connect_timeout_seconds,
            read_timeout=settings.storage_s3_read_timeout_seconds,
            retries={"max_attempts": 1, "mode": "standard"},
        ),
    )


def _upload_document_bytes(
    *,
    object_key: str,
    content: bytes,
    content_type: str,
    metadata: dict[str, str] | None = None,
) -> StorageUploadResult:
    client = _get_s3_client()
    put_result = client.put_object(
        Bucket=settings.storage_s3_bucket_name,
        Key=object_key,
        Body=content,
        ContentType=content_type,
        Metadata=metadata or {},
    )
    presigned_url = client.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": settings.storage_s3_bucket_name,
            "Key": object_key,
        },
        ExpiresIn=settings.storage_s3_presign_ttl_seconds,
    )
    expires_at = (
        datetime.now(UTC) + timedelta(seconds=settings.storage_s3_presign_ttl_seconds)
    ).isoformat()
    etag = put_result.get("ETag")
    if isinstance(etag, str):
        etag = etag.strip('"')

    return StorageUploadResult(
        bucket=settings.storage_s3_bucket_name,
        object_key=object_key,
        url=presigned_url,
        expires_at=expires_at,
        etag=etag,
    )


async def upload_document_bytes(
    *,
    object_key: str,
    content: bytes,
    content_type: str,
    metadata: dict[str, str] | None = None,
) -> StorageUploadResult:
    if not is_object_storage_configured():
        return StorageUploadResult(
            fallback_reason="S3-compatible object storage is not configured.",
        )

    circuit_reason = get_open_circuit_reason(OBJECT_STORAGE_PROVIDER_NAME)
    if circuit_reason:
        return StorageUploadResult(
            fallback_reason=(
                "Object storage circuit breaker is open because of a recent "
                f"upload failure. {circuit_reason}"
            ),
        )

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                _upload_document_bytes,
                object_key=object_key,
                content=content,
                content_type=content_type,
                metadata=metadata,
            ),
            timeout=(
                settings.storage_s3_connect_timeout_seconds
                + settings.storage_s3_read_timeout_seconds
                + 2
            ),
        )
    except TimeoutError:
        reason = (
            "Object storage upload timed out after "
            f"{settings.storage_s3_connect_timeout_seconds + settings.storage_s3_read_timeout_seconds + 2} seconds."
        )
        open_provider_circuit(OBJECT_STORAGE_PROVIDER_NAME, reason)
        return StorageUploadResult(fallback_reason=reason)
    except Exception as exc:
        reason = str(exc).strip() or "Object storage upload failed."
        open_provider_circuit(OBJECT_STORAGE_PROVIDER_NAME, reason)
        return StorageUploadResult(fallback_reason=reason)

    close_provider_circuit(OBJECT_STORAGE_PROVIDER_NAME)
    return result
