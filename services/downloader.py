import asyncio
import os
import json
import re
import glob
import logging
from dataclasses import dataclass
from typing import Optional
from config import config
import shutil
import sys

logger = logging.getLogger("smdownbot.downloader")

# Find yt-dlp: prefer venv copy, fallback to system
YTDLP = os.path.join(os.path.dirname(sys.executable), "yt-dlp")
if not os.path.exists(YTDLP):
    YTDLP = shutil.which("yt-dlp") or "yt-dlp"

@dataclass
class DownloadResult:
    success: bool
    file_path: Optional[str] = None
    title: Optional[str] = None
    duration: Optional[int] = None
    file_size: Optional[int] = None
    thumbnail: Optional[str] = None
    platform: Optional[str] = None
    error: Optional[str] = None
    formats: Optional[list] = None

def _base_opts(platform: str = None) -> dict:
    opts = {
        "quiet": True,
        "no-warnings": True,
        "no-playlist": True,
        "output": os.path.join(config.DOWNLOAD_DIR, "%(id)s.%(ext)s"),
        "socket-timeout": 30,
        "retries": 3,
    }
    cookie_file = os.path.join(config.COOKIES_DIR, f"{platform}.txt")
    if os.path.exists(cookie_file):
        opts["cookies"] = cookie_file
    return opts

def _is_auth_error(stderr: str) -> bool:
    """Check if error indicates expired/invalid cookies."""
    auth_patterns = [
        "You need to log in",
        "login required",
        "authentication",
        "HTTP Error 401",
        "HTTP Error 403",
        "Private content",
    ]
    lower = stderr.lower()
    return any(p.lower() in lower for p in auth_patterns)


async def get_info(url: str, platform: str = None, _retry: bool = True) -> Optional[dict]:
    """Get video info without downloading."""
    cmd = [YTDLP, "--dump-json", "--no-download", "--no-playlist"]

    # Only pass CLI-compatible options
    cookie_file = os.path.join(config.COOKIES_DIR, f"{platform}.txt")
    if os.path.exists(cookie_file):
        cmd.extend(["--cookies", cookie_file])

    cmd.append(url)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
    if proc.returncode != 0:
        err = stderr.decode()
        if _retry and platform == "instagram" and _is_auth_error(err):
            logger.info("Auth error in get_info, auto-refreshing cookies...")
            from services.cookies import handle_auth_failure
            if await handle_auth_failure():
                return await get_info(url, platform, _retry=False)
        return None
    try:
        return json.loads(stdout.decode())
    except json.JSONDecodeError:
        return None

async def download(url: str, platform: str = None, audio_only: bool = False, quality: str = "best") -> DownloadResult:
    """Download video/audio via yt-dlp."""
    os.makedirs(config.DOWNLOAD_DIR, exist_ok=True)
    opts = _base_opts(platform)

    if audio_only:
        opts.update({
            "format": "bestaudio/best",
            "extract-audio": True,
            "audio-format": "mp3",
            "audio-quality": "192",
        })
    else:
        if quality == "720":
            opts["format"] = "bestvideo[height<=720]+bestaudio/best[height<=720]/best"
        elif quality == "480":
            opts["format"] = "bestvideo[height<=480]+bestaudio/best[height<=480]/best"
        else:
            opts["format"] = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"

    # TikTok: prefer no-watermark
    if platform == "tiktok":
        opts["format"] = "best"

    # Build command
    cmd = [YTDLP]
    for k, v in opts.items():
        flag = f"--{k.replace('_', '-')}"
        if isinstance(v, bool):
            if v:
                cmd.append(flag)
        elif isinstance(v, (str, int, float)):
            cmd.extend([flag, str(v)])
        elif isinstance(v, list):
            for item in v:
                cmd.extend([flag, json.dumps(item) if isinstance(item, dict) else str(item)])
        elif isinstance(v, dict):
            for dk, dv in v.items():
                cmd.extend([f"--{dk}", str(dv)])

    cmd.extend(["--print", "after_move:filepath"])
    cmd.append(url)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(
        proc.communicate(), timeout=config.YT_DLP_TIMEOUT
    )

    if proc.returncode != 0:
        err = stderr.decode().strip().split("\n")[-1]
        # Auto-refresh cookies on auth failure
        if platform == "instagram" and _is_auth_error(err):
            logger.info("Auth error in download, auto-refreshing cookies...")
            from services.cookies import handle_auth_failure
            if await handle_auth_failure():
                # Retry download with fresh cookies
                cookie_file = os.path.join(config.COOKIES_DIR, f"{platform}.txt")
                if os.path.exists(cookie_file):
                    opts["cookies"] = cookie_file
                    cmd = [YTDLP]
                    for k, v in opts.items():
                        flag = f"--{k.replace('_', '-')}"
                        if isinstance(v, bool):
                            if v:
                                cmd.append(flag)
                        elif isinstance(v, (str, int, float)):
                            cmd.extend([flag, str(v)])
                        elif isinstance(v, list):
                            for item in v:
                                cmd.extend([flag, json.dumps(item) if isinstance(item, dict) else str(item)])
                        elif isinstance(v, dict):
                            for dk, dv in v.items():
                                cmd.extend([f"--{dk}", str(dv)])
                    cmd.extend(["--print", "after_move:filepath"])
                    cmd.append(url)

                    proc = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, stderr = await asyncio.wait_for(
                        proc.communicate(), timeout=config.YT_DLP_TIMEOUT
                    )
                    if proc.returncode == 0:
                        filepath = stdout.decode().strip().split("\n")[-1]
                        if os.path.exists(filepath):
                            file_size = os.path.getsize(filepath)
                            info = await get_info(url, platform, _retry=False)
                            return DownloadResult(
                                success=True,
                                file_path=filepath,
                                title=(info.get("title", "Download") if info else "Download")[:100],
                                duration=info.get("duration") if info else None,
                                file_size=file_size,
                                thumbnail=info.get("thumbnail") if info else None,
                                platform=platform,
                            )
                    err = stderr.decode().strip().split("\n")[-1]
        return DownloadResult(success=False, error=err[:200])

    filepath = stdout.decode().strip().split("\n")[-1]
    if not os.path.exists(filepath):
        return DownloadResult(success=False, error="File not found after download")

    file_size = os.path.getsize(filepath)

    # Get title from info
    info = await get_info(url, platform)
    title = info.get("title", "Download") if info else "Download"
    duration = info.get("duration") if info else None
    thumbnail = info.get("thumbnail") if info else None

    return DownloadResult(
        success=True,
        file_path=filepath,
        title=title[:100],
        duration=duration,
        file_size=file_size,
        thumbnail=thumbnail,
        platform=platform,
    )

def cleanup_file(path: str):
    """Delete downloaded file."""
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass

def cleanup_old_files(max_age_hours: int = 1):
    """Clean files older than max_age_hours."""
    import time
    now = time.time()
    cutoff = now - (max_age_hours * 3600)
    for f in glob.glob(os.path.join(config.DOWNLOAD_DIR, "*")):
        if os.path.getmtime(f) < cutoff:
            try:
                os.remove(f)
            except OSError:
                pass


def split_video(file_path: str, max_size_mb: int = 48) -> list[str]:
    """Split a video into parts that fit under max_size_mb.
    Returns list of part file paths."""
    import subprocess
    
    file_size = os.path.getsize(file_path)
    max_bytes = max_size_mb * 1024 * 1024
    
    if file_size <= max_bytes:
        return [file_path]
    
    # Get video duration
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", file_path],
        capture_output=True, text=True
    )
    duration = float(result.stdout.strip())
    
    # Calculate number of parts needed
    num_parts = int(file_size / max_bytes) + 1
    segment_duration = duration / num_parts
    
    # Split using ffmpeg
    base, ext = os.path.splitext(file_path)
    pattern = f"{base}_part%d{ext}"
    
    subprocess.run([
        "ffmpeg", "-i", file_path,
        "-c", "copy",
        "-f", "segment",
        "-segment_time", str(segment_duration),
        "-reset_timestamps", "1",
        pattern
    ], capture_output=True, check=True)
    
    # Collect part files
    parts = sorted(glob.glob(f"{base}_part*{ext}"))
    return parts if parts else [file_path]
