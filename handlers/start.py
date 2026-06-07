from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import CommandStart, Command
from database.db import get_or_create_user
from keyboards.inline import buy_keyboard

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    await get_or_create_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
    )
    await message.answer(
        "🎬 <b>Social Media Downloader</b>\n\n"
        "Send me a link from:\n"
        "🔴 YouTube — videos, shorts, audio\n"
        "📸 Instagram — posts, reels, stories\n"
        "🎵 TikTok — videos, with/without watermark\n\n"
        "Just paste any link and I'll handle the rest! ✨\n\n"
        "📋 /help — How to use\n"
        "⭐ /buy — Extra downloads\n"
        "📊 /stats — Your stats",
        parse_mode="HTML",
    )

@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📖 <b>How to use</b>\n\n"
        "1️⃣ Copy a link from YouTube, Instagram, or TikTok\n"
        "2️⃣ Paste it here in chat\n"
        "3️⃣ Choose quality (if available)\n"
        "4️⃣ Wait for download — I'll send your file!\n\n"
        "💡 <b>Tips:</b>\n"
        "• YouTube: choose video quality or audio-only\n"
        "• TikTok: get videos without watermark\n"
        "• Instagram: public posts & reels work, stories need cookies\n\n"
        "📊 <b>Limits:</b> 20 downloads/day (free)\n"
        "⭐ Buy extra with Telegram Stars — /buy",
        parse_mode="HTML",
    )

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    user = await get_or_create_user(message.from_user.id)
    limit = user["daily_limit"] or 20
    used = user["downloads_today"]
    extra = user["extra_downloads"]
    remaining = "∞" if limit == 0 else str(limit - used + extra)
    await message.answer(
        f"📊 <b>Your Stats</b>\n\n"
        f"📥 Used today: {used}/{limit if limit else '∞'}\n"
        f"🎁 Extra remaining: {extra}\n"
        f"📉 Remaining today: {remaining}",
        parse_mode="HTML",
    )

@router.message(Command("buy"))
async def cmd_buy(message: Message):
    await message.answer(
        "⭐ <b>Extra Downloads</b>\n\n"
        "Get 10 extra downloads for today!\n"
        "Price: 50 Telegram Stars\n\n"
        "Tap below to purchase:",
        parse_mode="HTML",
        reply_markup=buy_keyboard(),
    )
