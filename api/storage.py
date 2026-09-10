"""Cloudflare R2 storage via boto3 S3-compatible API, with seamless local fallback."""

import os
import boto3

R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "")
R2_BUCKET = os.environ.get("R2_BUCKET", "")
R2_PUBLIC_URL = os.environ.get("R2_PUBLIC_URL", "")

LOCAL_STORAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scratch", "storage")

_endpoint = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com" if R2_ACCOUNT_ID else None

_client = None
if R2_ACCOUNT_ID and R2_BUCKET:
    try:
        _client = boto3.client(
            "s3",
            endpoint_url=_endpoint,
            aws_access_key_id=os.environ.get("R2_ACCESS_KEY_ID", ""),
            aws_secret_access_key=os.environ.get("R2_SECRET_ACCESS_KEY", ""),
            region_name="auto",
        )
    except Exception:
        _client = None


def put_pdf(sha: str, data: bytes) -> str:
    key = f"docs/{sha}.pdf"
    if R2_BUCKET and _client:
        _client.put_object(Bucket=R2_BUCKET, Key=key, Body=data, ContentType="application/pdf")
    else:
        path = os.path.join(LOCAL_STORAGE_DIR, key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
    return key


def put_page_png(doc_id: str, page: int, data: bytes) -> str:
    key = f"pages/{doc_id}/{page}.png"
    if R2_BUCKET and _client:
        _client.put_object(Bucket=R2_BUCKET, Key=key, Body=data, ContentType="image/png")
    else:
        path = os.path.join(LOCAL_STORAGE_DIR, key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
    return key


def public_url(key: str) -> str:
    if R2_PUBLIC_URL:
        return f"{R2_PUBLIC_URL.rstrip('/')}/{key}"
    return f"/pages/{key}"


def get_object_bytes(key: str) -> bytes:
    """Fetch raw object bytes from R2 or local storage directly into memory."""
    if R2_BUCKET and _client:
        resp = _client.get_object(Bucket=R2_BUCKET, Key=key)
        return resp["Body"].read()

    path = os.path.join(LOCAL_STORAGE_DIR, key)
    with open(path, "rb") as f:
        return f.read()
