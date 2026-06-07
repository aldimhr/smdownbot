"""Bulk Instagram stories download."""
import asyncio
import json
import os
from dataclasses import dataclass
from config import config

YTDLP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".venv", "bin", "yt-dlp")
if not os.path.exists(YTDLP):
    import shutil
    YTDLP = shutil.which("yt-dlp") or "yt-dlp"

@dataclass
class StoryItem:
    id: str
    title: str
    duration: float = 0
    url: str = ""

async def get_stories_list(username_url: str) -> list[StoryItem]:
    """Get list of available stories for a user."""
    cookie_file = os.path.join(config.COOKIES_DIR, "instagram.txt")
    cmd = [YTDLP, "--dump-json", "--flat-playlist", "--no-download"]
    if os.path.exists(cookie_file):
        cmd.extend(["--cookies", cookie_file])
    cmd.append(username_url)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)

    if proc.returncode != 0:
        return []

    stories = []
    for line in stdout.decode().strip().split("\n"):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            stories.append(StoryItem(
                id=data.get("id", ""),
                title=data.get("title", "Story"),
                duration=data.get("duration", 0),
                url=data.get("url", ""),
            ))
        except json.JSONDecodeError:
            continue
    return stories

async def download_story(story_url: str) -> dict:
    """Download a single story. Returns {success, file_path, title, file_size, error}."""
    from services.downloader import download
    result = await download(story_url, "instagram")
    return {
        "success": result.success,
        "file_path": result.file_path,
        "title": result.title,
        "file_size": result.file_size,
        "duration": result.duration,
        "error": result.error,
    }
