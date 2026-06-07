#!/usr/bin/env python3
import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import config
from database.models import init_db
from handlers import start, download, admin, stars

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("smdownbot")

async def on_startup(bot: Bot):
    os.makedirs(config.DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(config.COOKIES_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    await init_db(config.DB_PATH)
    logger.info("Bot started. DB initialized.")

async def main():
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    dp.include_routers(
        stars.router,   # Stars payment handlers first
        start.router,
        download.router,
        admin.router,
    )

    dp.startup.register(on_startup)

    logger.info("Starting polling...")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query", "inline_query", "pre_checkout_query"])

if __name__ == "__main__":
    asyncio.run(main())
