import aiosqlite
from datetime import date, datetime
from config import config

async def get_db():
    db = await aiosqlite.connect(config.DB_PATH)
    db.row_factory = aiosqlite.Row
    return db

async def get_or_create_user(user_id: int, username: str = None, first_name: str = None):
    db = await get_db()
    try:
        today = date.today().isoformat()
        row = await db.execute_fetchall(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        )
        if not row:
            await db.execute(
                "INSERT INTO users (user_id, username, first_name, last_reset) VALUES (?, ?, ?, ?)",
                (user_id, username, first_name, today)
            )
            await db.commit()
            return {"user_id": user_id, "downloads_today": 0, "daily_limit": config.DAILY_LIMIT, "extra_downloads": 0, "is_banned": 0}
        user = dict(row[0])
        # Reset daily counter if new day
        if user["last_reset"] != today:
            await db.execute(
                "UPDATE users SET downloads_today = 0, last_reset = ? WHERE user_id = ?",
                (today, user_id)
            )
            await db.commit()
            user["downloads_today"] = 0
        return user
    finally:
        await db.close()

async def can_download(user_id: int) -> tuple[bool, str]:
    user = await get_or_create_user(user_id)
    if user["is_banned"]:
        return False, "🚫 You are banned."
    limit = user["daily_limit"] or config.DAILY_LIMIT
    if user["daily_limit"] == 0:  # 0 = unlimited
        return True, ""
    used = user["downloads_today"]
    extra = user["extra_downloads"]
    remaining = limit - used + extra
    if remaining <= 0:
        return False, f"📭 Daily limit reached ({limit}/day).\n\n⭐ Buy {config.STARS_EXTRA_DOWNLOADS} extra downloads for {config.STARS_PRICE} Stars — /buy"
    return True, ""

async def record_download(user_id: int, url: str, platform: str, title: str = None, file_size: int = 0):
    db = await get_db()
    try:
        today = date.today().isoformat()
        await db.execute(
            "INSERT INTO downloads (user_id, url, platform, title, file_size) VALUES (?, ?, ?, ?, ?)",
            (user_id, url, platform, title, file_size)
        )
        await db.execute(
            "UPDATE users SET downloads_today = downloads_today + 1 WHERE user_id = ?",
            (user_id,)
        )
        # Update daily stats
        await db.execute(
            """INSERT INTO stats (date, total_downloads, by_platform)
               VALUES (?, 1, ?)
               ON CONFLICT(date) DO UPDATE SET
               total_downloads = total_downloads + 1,
               by_platform = json_set(by_platform, '$.' || ?, COALESCE(json_extract(by_platform, '$.' || ?), 0) + 1)""",
            (today, f'{{"{platform}": 1}}', platform, platform)
        )
        await db.commit()
    finally:
        await db.close()

async def add_extra_downloads(user_id: int, count: int):
    db = await get_db()
    try:
        await db.execute(
            "UPDATE users SET extra_downloads = extra_downloads + ? WHERE user_id = ?",
            (count, user_id)
        )
        await db.commit()
    finally:
        await db.close()

async def use_extra_download(user_id: int):
    db = await get_db()
    try:
        await db.execute(
            "UPDATE users SET extra_downloads = MAX(0, extra_downloads - 1) WHERE user_id = ?",
            (user_id,)
        )
        await db.commit()
    finally:
        await db.close()

async def get_stats():
    db = await get_db()
    try:
        today = date.today().isoformat()
        total_users = await db.execute_fetchall("SELECT COUNT(*) FROM users")
        today_downloads = await db.execute_fetchall(
            "SELECT COUNT(*) FROM downloads WHERE date(created_at) = ?", (today,)
        )
        total_downloads = await db.execute_fetchall("SELECT COUNT(*) FROM downloads")
        return {
            "total_users": total_users[0][0],
            "today_downloads": today_downloads[0][0],
            "total_downloads": total_downloads[0][0],
        }
    finally:
        await db.close()

async def ban_user(user_id: int, ban: bool = True):
    db = await get_db()
    try:
        await db.execute("UPDATE users SET is_banned = ? WHERE user_id = ?", (1 if ban else 0, user_id))
        await db.commit()
    finally:
        await db.close()
