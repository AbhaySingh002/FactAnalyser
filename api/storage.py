"""Cloudflare R2 storage via boto3 S3-compatible API."""

import os

import boto3

R2_ACCOUNT_ID = os.environ["R2_ACCOUNT_ID"]
R2_BUCKET = os.environ["R2_BUCKET"]
R2_PUBLIC_URL = os.environ.get("R2_PUBLIC_URL", "")

_client = boto3.client(
    "s3",
    endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
    aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
    region_name="auto",
)


def put_pdf(sha: str, data: bytes) -> str:
    key = f"docs/{sha}.pdf"
    _client.put_object(Bucket=R2_BUCKET, Key=key, Body=data, ContentType="application/pdf")
    return key


def put_page_png(doc_id: str, page: int, data: bytes) -> str:
    key = f"pages/{doc_id}/{page}.png"
    _client.put_object(Bucket=R2_BUCKET, Key=key, Body=data, ContentType="image/png")
    return key


def public_url(key: str) -> str:
    return f"{R2_PUBLIC_URL.rstrip('/')}/{key}"


def get_object_bytes(key: str) -> bytes:
    """Fetch raw object bytes from R2 directly into memory (stateless)."""
    resp = _client.get_object(Bucket=R2_BUCKET, Key=key)
    return resp["Body"].read()

