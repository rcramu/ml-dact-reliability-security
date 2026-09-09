"""S3-compatible object storage via MinIO (req.md Sec. 28, 54 — 'Amazon S3')."""
import json
import logging

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError

from ..config import settings

logger = logging.getLogger("churnplatform.s3")

_client = None


def get_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            config=BotoConfig(signature_version="s3v4"),
            region_name=settings.s3_region,
        )
    return _client


def ensure_bucket():
    client = get_client()
    try:
        client.head_bucket(Bucket=settings.s3_bucket)
    except ClientError:
        client.create_bucket(Bucket=settings.s3_bucket)
        logger.info("Created S3 bucket %s", settings.s3_bucket)


def put_json(key: str, payload: dict) -> str:
    client = get_client()
    client.put_object(Bucket=settings.s3_bucket, Key=key, Body=json.dumps(payload, default=str).encode("utf-8"), ContentType="application/json")
    return f"s3://{settings.s3_bucket}/{key}"


def put_text(key: str, text: str, content_type: str = "text/csv") -> str:
    client = get_client()
    client.put_object(Bucket=settings.s3_bucket, Key=key, Body=text.encode("utf-8"), ContentType=content_type)
    return f"s3://{settings.s3_bucket}/{key}"


def list_objects(prefix: str, limit: int = 100) -> list[dict]:
    client = get_client()
    resp = client.list_objects_v2(Bucket=settings.s3_bucket, Prefix=prefix, MaxKeys=limit)
    return [
        {"key": obj["Key"], "size": obj["Size"], "last_modified": obj["LastModified"].isoformat()}
        for obj in resp.get("Contents", [])
    ]


def get_text(key: str) -> str:
    client = get_client()
    obj = client.get_object(Bucket=settings.s3_bucket, Key=key)
    return obj["Body"].read().decode("utf-8")
