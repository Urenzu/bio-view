from pathlib import Path
from typing import Iterator
import boto3
from botocore.config import Config
from app.config import settings


def s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=settings.aws_access_key,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
        config=Config(retries={"max_attempts": 5, "mode": "standard"}),
    )


def _year_from_month_prefix(sub: str) -> int | None:
    """`Current_Content/January_2026/` -> 2026."""
    name = sub.strip("/").rsplit("/", 1)[-1]
    parts = name.split("_")
    if len(parts) >= 2 and parts[-1].isdigit():
        return int(parts[-1])
    return None


def list_meca_keys_by_month(
    bucket: str, prefix: str, min_year: int
) -> dict[str, list[str]]:
    """Returns {month_prefix: [meca_keys]} for every <prefix><Month>_<YYYY>/
    where YYYY >= min_year."""
    s3 = s3_client()
    paginator = s3.get_paginator("list_objects_v2")

    month_prefixes: list[str] = []
    for page in paginator.paginate(
        Bucket=bucket, Prefix=prefix, Delimiter="/", RequestPayer="requester"
    ):
        for cp in page.get("CommonPrefixes", []):
            sub = cp["Prefix"]
            y = _year_from_month_prefix(sub)
            if y is not None and y >= min_year:
                month_prefixes.append(sub)

    result: dict[str, list[str]] = {}
    for mp in sorted(month_prefixes):
        keys: list[str] = []
        for page in paginator.paginate(Bucket=bucket, Prefix=mp, RequestPayer="requester"):
            for obj in page.get("Contents", []):
                if obj["Key"].endswith(".meca"):
                    keys.append(obj["Key"])
        result[mp] = keys
    return result


def list_meca_keys(
    bucket: str, prefix: str, min_year: int | None = None
) -> Iterator[tuple[str, int]]:
    """List MECA keys under prefix. If min_year is set, only walks
    `<prefix><Month>_<YYYY>/` subdirs where YYYY >= min_year.
    """
    s3 = s3_client()
    paginator = s3.get_paginator("list_objects_v2")

    if min_year is None:
        for page in paginator.paginate(
            Bucket=bucket, Prefix=prefix, RequestPayer="requester"
        ):
            for obj in page.get("Contents", []):
                if obj["Key"].endswith(".meca"):
                    yield obj["Key"], obj["Size"]
        return

    month_prefixes: list[str] = []
    for page in paginator.paginate(
        Bucket=bucket, Prefix=prefix, Delimiter="/", RequestPayer="requester"
    ):
        for cp in page.get("CommonPrefixes", []):
            sub = cp["Prefix"]
            y = _year_from_month_prefix(sub)
            if y is not None and y >= min_year:
                month_prefixes.append(sub)

    for mp in sorted(month_prefixes):
        for page in paginator.paginate(
            Bucket=bucket, Prefix=mp, RequestPayer="requester"
        ):
            for obj in page.get("Contents", []):
                if obj["Key"].endswith(".meca"):
                    yield obj["Key"], obj["Size"]


def download_meca(bucket: str, key: str, dest_path: Path) -> int:
    s3 = s3_client()
    resp = s3.get_object(Bucket=bucket, Key=key, RequestPayer="requester")
    body = resp["Body"].read()
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(body)
    return len(body)
