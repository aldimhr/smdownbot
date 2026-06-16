import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from config import config
from database.db import create_direct_link, cleanup_expired_direct_links, list_active_direct_link_paths


@dataclass
class PublishedDirectLink:
    token: str
    url: str
    file_path: str
    expires_at: datetime
    file_size: int
    title: str


def _normalize_path_prefix(path_prefix: str) -> str:
    return path_prefix.strip("/")


def is_large_or_long(info: dict | None, file_size: int | None = None) -> bool:
    if file_size is not None and file_size > config.MAX_FILE_SIZE:
        return True
    if not info:
        return False
    duration = info.get("duration")
    return bool(duration and duration >= config.LONG_VIDEO_THRESHOLD_SECONDS)


def build_direct_link_url(token: str, ext: str) -> str:
    base = config.DIRECT_LINK_URL_BASE.rstrip("/")
    prefix = _normalize_path_prefix(config.DIRECT_LINK_URL_PATH)
    filename = f"{token}.{ext.lstrip('.')}"
    if prefix:
        return f"{base}/{prefix}/{quote(filename)}"
    return f"{base}/{quote(filename)}"


def _expired_cutoff_timestamp() -> float:
    return (datetime.now(timezone.utc) - timedelta(hours=config.DIRECT_LINK_TTL_HOURS)).timestamp()


def _cleanup_stale_files(directory: Path, *, cutoff: float, keep_paths: set[Path] | None = None) -> int:
    if not directory.exists():
        return 0
    keep_paths = keep_paths or set()
    removed = 0
    for path in directory.iterdir():
        if not path.is_file():
            continue
        resolved = path.resolve()
        if resolved in keep_paths:
            continue
        try:
            if path.stat().st_mtime <= cutoff:
                path.unlink()
                removed += 1
        except FileNotFoundError:
            continue
    return removed


async def cleanup_direct_link_artifacts() -> dict[str, int]:
    removed_db = await cleanup_expired_direct_links()
    public_dir = Path(config.DIRECT_LINK_DIR)
    active_paths = {Path(p).resolve() for p in await list_active_direct_link_paths() if p}
    cutoff = _expired_cutoff_timestamp()
    removed_orphans = _cleanup_stale_files(public_dir, cutoff=cutoff, keep_paths=active_paths)
    removed_working = _cleanup_stale_files(Path(config.DOWNLOAD_DIR), cutoff=cutoff)

    return {
        "removed_db": removed_db,
        "removed_orphans": removed_orphans,
        "removed_working": removed_working,
    }


async def publish_direct_link(source_path: str, user_id: int, platform: str, title: str, file_size: int) -> PublishedDirectLink:
    await cleanup_direct_link_artifacts()
    os.makedirs(config.DIRECT_LINK_DIR, exist_ok=True)

    token = secrets.token_hex(16)
    _, ext = os.path.splitext(source_path)
    ext = ext or ".bin"
    dest_path = os.path.join(config.DIRECT_LINK_DIR, f"{token}{ext}")
    os.replace(source_path, dest_path)
    os.chmod(dest_path, 0o644)

    expires_at = datetime.now(timezone.utc) + timedelta(hours=config.DIRECT_LINK_TTL_HOURS)
    expires_iso = expires_at.isoformat()
    await create_direct_link(token, user_id, platform, title, dest_path, file_size, expires_iso)

    return PublishedDirectLink(
        token=token,
        url=build_direct_link_url(token, ext),
        file_path=dest_path,
        expires_at=expires_at,
        file_size=file_size,
        title=title,
    )
