"""AWS S3 upload/delete helpers (sync boto3 wrapped in asyncio.to_thread)."""

import asyncio
import logging
import mimetypes
import uuid
from typing import Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)


def _get_s3_client():
    return boto3.client(
        "s3",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )


def _upload_sync(content: bytes, key: str, content_type: str) -> str:
    """Blocking S3 PutObject. Returns the public URL."""
    client = _get_s3_client()
    client.put_object(
        Bucket=settings.s3_bucket_name,
        Key=key,
        Body=content,
        ContentType=content_type,
    )
    if settings.s3_base_url:
        base = settings.s3_base_url.rstrip("/")
        return f"{base}/{key}"
    return f"https://{settings.s3_bucket_name}.s3.{settings.aws_region}.amazonaws.com/{key}"


def _delete_sync(key: str) -> None:
    """Blocking S3 DeleteObject."""
    client = _get_s3_client()
    client.delete_object(Bucket=settings.s3_bucket_name, Key=key)


async def upload_image_to_s3(
    content: bytes,
    filename: str,
    tenant_id: str,
    lecture_id: str,
) -> str:
    """
    Upload image bytes to S3 under lecture-images/{tenant_id}/{lecture_id}/{uuid}{ext}.
    Returns the public HTTPS URL.
    """
    if not settings.s3_bucket_name or not settings.aws_access_key_id:
        raise RuntimeError("S3 is not configured. Set AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, S3_BUCKET_NAME in .env")

    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ".jpg"
    key = f"lecture-images/{tenant_id}/{lecture_id}/{uuid.uuid4()}{ext}"
    content_type = mimetypes.guess_type(filename)[0] or "image/jpeg"

    url = await asyncio.to_thread(_upload_sync, content, key, content_type)
    logger.info("Uploaded image to S3: %s", key)
    return url


async def delete_image_from_s3(image_url: str) -> None:
    """
    Delete an image from S3 given its URL.
    Silently skips if not an S3 URL or if deletion fails.
    """
    if not settings.s3_bucket_name or not settings.aws_access_key_id:
        return
    if not image_url or not image_url.startswith("http"):
        return  # local /tmp path — nothing to delete on S3

    try:
        # Extract the key from the URL
        if settings.s3_base_url and image_url.startswith(settings.s3_base_url):
            key = image_url[len(settings.s3_base_url):].lstrip("/")
        else:
            # Standard S3 URL: https://bucket.s3.region.amazonaws.com/key
            key = "/".join(image_url.split("/")[3:])

        if key:
            await asyncio.to_thread(_delete_sync, key)
            logger.info("Deleted image from S3: %s", key)
    except (BotoCoreError, ClientError) as e:
        logger.warning("S3 delete failed for %s: %s", image_url, e)
    except Exception as e:
        logger.warning("Unexpected error deleting S3 object %s: %s", image_url, e)
