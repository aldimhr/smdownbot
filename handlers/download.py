import asyncio
import os
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.filters import Command
from database.db import can_download, record_download, use_extra_download
from services.platform import detect_platform, get_platform_info
from services.downloader import download, get_info, cleanup_file, DownloadResult
from services.limiter import is_downloading, set_active, clear_active, cancel_download
from keyboards.inline import quality_keyboard, cancel_keyboard
from config import config
from services.url_store import store_url, get_url
from services.bulk_stories import get_stories_list

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

@router.message(F.text.regexp(r"^@[\w.]{1,30}$"))
async def handle_username(message: Message, bot: Bot):
    """Handle @username - fetch all Instagram stories."""
    user_id = message.from_user.id
    username = message.text.strip().lstrip("@")

    # Check daily limit
    ok, err = await can_download(user_id)
    if not ok:
        await message.answer(err)
        return

    url = f"https://www.instagram.com/stories/{username}/"
    await handle_bulk_stories(message, bot, url, user_id)


async def handle_bulk_stories(message: Message, bot: Bot, url: str, user_id: int):
    """Handle bulk story download for instagram.com/stories/username/"""
    import re
    match = re.search(r"stories/([\w.]+)", url)
    username = match.group(1) if match else "user"

    loading = await message.answer("🔍 Fetching stories list...")

    stories = await get_stories_list(url)
    if not stories:
        await loading.edit_text("❌ No stories found for this user.")
        return

    total = len(stories)
    note = ""
    if total <= 8:
        note = "\n\n💡 <i>Note: Some stories may not be visible if the bot doesn't follow this user.</i>"
    await loading.edit_text(f"📖 Found {total} stories from this user. Starting download...{note}")

    downloaded = 0
    failed = 0

    for story in stories:
        i = story.index
        # Check daily limit
        ok, err = await can_download(user_id)
        if not ok:
            await message.answer(f"⚠️ Daily limit reached after {downloaded} downloads.\n{err}")
            break

        # Check if cancelled
        if is_downloading(user_id) and cancel_download(user_id):
            await message.answer(f"❌ Cancelled after {downloaded}/{total} stories.")
            return

        # Update progress
        progress_msg = await message.answer(f"📥 Downloading story {i}/{total}...")

        # Download using playlist index (not media ID — that causes duplicates)
        from services.bulk_stories import download_story_by_index
        from services.downloader import cleanup_file
        result = await download_story_by_index(url, i)

        if not result["success"]:
            failed += 1
            err_msg = result["error"][:50] if result["error"] else "Unknown error"
            await progress_msg.edit_text(f"❌ Story {i}/{total} failed: {err_msg}")
            continue

        file_path = result["file_path"]
        file_size = result["file_size"]

        # Check size
        if file_size > config.MAX_FILE_SIZE:
            cleanup_file(file_path)
            failed += 1
            await progress_msg.edit_text(f"❌ Story {i}/{total} too large ({file_size // (1024*1024)}MB)")
            continue

        # Send
        try:
            caption = f"📖 Story {i}/{total}"
            if result["title"]:
                caption += f" — {result['title'][:50]}"

            file = FSInputFile(file_path)
            await bot.send_video(
                chat_id=user_id,
                video=file,
                caption=caption,
                parse_mode="HTML",
                supports_streaming=True,
            )
            downloaded += 1
            await record_download(user_id, url, "instagram", result["title"], file_size)
            await progress_msg.delete()
        except Exception as e:
            failed += 1
            await progress_msg.edit_text(f"❌ Story {i}/{total} upload failed: {str(e)[:50]}")
        finally:
            cleanup_file(file_path)

    # Summary
    summary = f"✅ Downloaded {downloaded}/{total} stories"
    if failed:
        summary += f" ({failed} failed)"
    await message.answer(summary)


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

    # Check for bulk stories (instagram.com/stories/username/ without specific story ID)
    if platform == "instagram" and "stories/" in url and not video_id.isdigit():
        await handle_bulk_stories(message, bot, url, user_id)
        return

    # Show info + quality options
    loading = await message.answer(f"🔍 Analyzing link... {pinfo.icon}")

    info = await get_info(url, platform)
    if not info:
        await loading.edit_text("❌ Couldn't fetch this content. It might be private, expired, or temporarily unavailable.")
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
        reply_markup=quality_keyboard(store_url(url, platform), platform),
    )

@router.callback_query(F.data.startswith("dl:"))
async def process_download(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id

    # Parse callback data: dl:quality:short_id
    parts = callback.data.split(":", 2)
    if len(parts) < 3:
        await callback.answer("Invalid request")
        return

    quality = parts[1]
    short_id = parts[2]

    await callback.answer()
    await process_quality_download(bot, user_id, quality, short_id, callback.message.chat.id, callback.message)


async def process_quality_download(bot: Bot, user_id: int, quality: str, short_id: str, chat_id: int, edit_msg=None):
    """Download logic shared between regular and premium (Stars-paid) downloads."""
    audio_only = quality == "audio"

    # Look up URL from store
    url_data = get_url(short_id)
    if not url_data:
        msg = "❌ Link expired. Please send the URL again."
        if edit_msg:
            await edit_msg.edit_text(msg)
        else:
            await bot.send_message(chat_id, msg)
        return
    url, platform = url_data

    # Re-check limit (skip for premium — they already paid)
    if quality not in ("1080", "4k"):
        ok, err = await can_download(user_id)
        if not ok:
            if edit_msg:
                await edit_msg.edit_text(err)
            else:
                await bot.send_message(chat_id, err)
            return

    # Start download
    status_msg = None
    if edit_msg:
        status_msg = await edit_msg.edit_text(
            "📥 <b>Downloading...</b>\n⏳ This may take a moment\n\n❌ /cancel to abort",
            parse_mode="HTML",
        )
    else:
        status_msg = await bot.send_message(
            chat_id,
            "📥 <b>Downloading...</b>\n⏳ This may take a moment\n\n❌ /cancel to abort",
            parse_mode="HTML",
        )

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

        file = FSInputFile(result.file_path)
        if audio_only:
            await bot.send_audio(
                chat_id=chat_id,
                audio=file,
                caption=caption,
                parse_mode="HTML",
            )
        else:
            await bot.send_video(
                chat_id=chat_id,
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
