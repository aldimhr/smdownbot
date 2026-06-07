import asyncio
import os
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InputFile
from aiogram.filters import Command
from database.db import can_download, record_download, use_extra_download
from services.platform import detect_platform, get_platform_info
from services.downloader import download, get_info, cleanup_file, DownloadResult
from services.limiter import is_downloading, set_active, clear_active, cancel_download
from keyboards.inline import quality_keyboard, cancel_keyboard
from config import config

router = Router()

def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"

def format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    else:
        return f"{seconds // 3600}h {(seconds % 3600) // 60}m"

@router.message(F.text.regexp(r"https?://\S+"))
async def handle_link(message: Message, bot: Bot):
    user_id = message.from_user.id
    url = message.text.strip()

    # Check if already downloading
    if is_downloading(user_id):
        await message.answer("⏳ You already have a download in progress. Wait or /cancel it first.")
        return

    # Check daily limit
    ok, err = await can_download(user_id)
    if not ok:
        await message.answer(err)
        return

    # Detect platform
    result = detect_platform(url)
    if not result:
        await message.answer("❌ I couldn't recognize that link.\nSupported: YouTube, Instagram, TikTok")
        return

    platform, video_id = result
    pinfo = get_platform_info(platform)

    # Show info + quality options
    loading = await message.answer(f"🔍 Analyzing link... {pinfo.icon}")

    info = await get_info(url, platform)
    if not info:
        await loading.edit_text("❌ Couldn't fetch video info. The link might be private or invalid.")
        return

    title = info.get("title", "Unknown")[:80]
    duration = info.get("duration")
    uploader = info.get("uploader", "")

    text = f"{pinfo.icon} <b>{title}</b>"
    if uploader:
        text += f"\n👤 {uploader}"
    if duration:
        text += f"\n⏱ {format_duration(duration)}"
    if pinfo.note:
        text += f"\n💡 {pinfo.note}"

    await loading.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=quality_keyboard(url, platform),
    )

@router.callback_query(F.data.startswith("dl:"))
async def process_download(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id

    # Parse callback data: dl:quality:url
    parts = callback.data.split(":", 2)
    if len(parts) < 3:
        await callback.answer("Invalid request")
        return

    quality = parts[1]
    url = parts[2]
    audio_only = quality == "audio"

    # Re-check limit
    ok, err = await can_download(user_id)
    if not ok:
        await callback.message.edit_text(err)
        await callback.answer()
        return

    result = detect_platform(url)
    platform = result[0] if result else "unknown"

    # Start download
    status_msg = await callback.message.edit_text(
        "📥 <b>Downloading...</b>\n⏳ This may take a moment\n\n❌ /cancel to abort",
        parse_mode="HTML",
    )
    await callback.answer()

    async def do_download():
        return await download(url, platform, audio_only=audio_only, quality=quality)

    task = asyncio.create_task(do_download())
    set_active(user_id, task)

    try:
        result = await task
    except asyncio.CancelledError:
        await status_msg.edit_text("❌ Download cancelled.")
        return
    finally:
        clear_active(user_id)

    if not result.success:
        error_text = result.error[:150] if result.error else "Unknown error"
        await status_msg.edit_text(f"❌ Download failed:\n<code>{error_text}</code>", parse_mode="HTML")
        return

    # Check file size
    if result.file_size > config.MAX_FILE_SIZE:
        cleanup_file(result.file_path)
        await status_msg.edit_text(
            f"❌ File too large ({format_size(result.file_size)}).\n"
            f"Telegram bot limit is 50MB.\n\n"
            f"Try a lower quality: 480p or audio-only.",
            parse_mode="HTML",
        )
        return

    # Send file
    await status_msg.edit_text("📤 Uploading to Telegram...", parse_mode="HTML")

    try:
        caption = f"🎬 <b>{result.title}</b>"
        if result.duration:
            caption += f"\n⏱ {format_duration(result.duration)}"
        caption += f"\n💾 {format_size(result.file_size)}"

        file = InputFile(result.file_path)
        if audio_only:
            await bot.send_audio(
                chat_id=user_id,
                audio=file,
                caption=caption,
                parse_mode="HTML",
            )
        else:
            await bot.send_video(
                chat_id=user_id,
                video=file,
                caption=caption,
                parse_mode="HTML",
                supports_streaming=True,
            )

        await record_download(user_id, url, platform, result.title, result.file_size)
        await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text(f"❌ Upload failed: {str(e)[:100]}")
    finally:
        cleanup_file(result.file_path)

@router.message(Command("cancel"))
async def cmd_cancel(message: Message):
    if cancel_download(message.from_user.id):
        await message.answer("✅ Download cancelled.")
    else:
        await message.answer("ℹ️ No active download to cancel.")

@router.callback_query(F.data == "cancel")
async def cancel_button(callback: CallbackQuery):
    if cancel_download(callback.from_user.id):
        await callback.message.edit_text("❌ Download cancelled.")
    await callback.answer()
