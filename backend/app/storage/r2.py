"""Cloudflare R2 access (S3-compatible) via boto3."""

import functools

import boto3
from botocore.client import Config

from app.config import settings


@functools.lru_cache(maxsize=1)
def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint(),
        aws_access_key_id=settings.r2_access_key_id(),
        aws_secret_access_key=settings.r2_secret_access_key(),
        # R2 ignores regions but boto3 requires one; "auto" is what R2 documents.
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def presign_put(key: str, content_length: int) -> str:
    """URL the browser can PUT the file to directly, bypassing our backend.

    ContentLength is signed in so the client cannot upload something larger
    than what we validated.
    """
    return _client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.r2_bucket(),
            "Key": key,
            "ContentLength": content_length,
        },
        ExpiresIn=settings.PRESIGN_EXPIRY_SECONDS,
    )


def object_exists(key: str) -> bool:
    """True if the object is there, False if it is genuinely absent.

    Only a not-found response counts as False. Anything else (bad credentials,
    wrong bucket, R2 outage) is re-raised: reporting an auth failure as "the
    user never uploaded the file" would send them chasing the wrong problem.
    """
    client = _client()
    try:
        client.head_object(Bucket=settings.r2_bucket(), Key=key)
        return True
    except client.exceptions.ClientError as err:
        status_code = err.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if status_code == 404:
            return False
        raise


def download(key: str) -> bytes:
    response = _client().get_object(Bucket=settings.r2_bucket(), Key=key)
    return response["Body"].read()
