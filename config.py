import os
from dataclasses import dataclass, field

@dataclass
class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    ADMIN_ID: int = int(os.getenv("ADMIN_ID", "519613720"))
    DB_PATH: str = os.getenv("DB_PATH", "data/smdown.db")
    DOWNLOAD_DIR: str = os.getenv("DOWNLOAD_DIR", "downloads")
    MAX_FILE_SIZE: int = 50 * 1024 * 1024       # 50MB Telegram bot limit
    PREMIUM_FILE_SIZE: int = 2 * 1024 * 1024 * 1024  # 2GB for premium
    DAILY_LIMIT: int = int(os.getenv("DAILY_LIMIT", "20"))
    STARS_EXTRA_DOWNLOADS: int = 10
    STARS_PRICE: int = 50  # Stars per extra pack
    YT_DLP_TIMEOUT: int = 300  # 5 min max per download
    COOKIES_DIR: str = "cookies"

config = Config()
