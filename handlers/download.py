import asyncio
import os
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, FSInputFile, ChatFullInfo
from aiogram.filters import Command
from database.db import can_download, record_download, use_extra_download
from services.platform import detect_platform, get_platform_info
from services.downloader import download, get_info, cleanup_file, split_video, DownloadResult
from services.direct_links import is_large_or_long, publish_direct_link
from services.limiter import is_downloading, set_active, clear_active, cancel_download
from keyboards.inline import quality_keyboard, cancel_keyboard, direct_link_keyboard
from handlers.admin import is_admin
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


def is_admin_user(user_id: int) -> bool:
    return is_admin(user_id)


def direct_link_offer_text(title: str, duration: int | None, is_admin_request: bool) -> str:
    text = (
        f"🎬 <b>{title}</b>\n"
        f"📦 Too large for normal Telegram delivery."
    )
    if duration:
        text += f"\n⏱ {format_duration(duration)}"
    text += f"\n\n🔗 You can receive this as <b>one downloadable file</b> via a temporary direct link."
    if is_admin_request:
        text += (
            "\n\n👑 Admin bypass is active for this request."
            f"\n📢 You can also upload it directly to <b>{config.ADMIN_UPLOAD_CHANNEL}</b>."
        )
    else:
        text += f"\n\n⭐ Price: <b>{config.STARS_DIRECT_LINK} Stars</b>"
    return text


def _public_channel_username(channel: str) -> str:
    value = channel.strip()
    if value.startswith("https://t.me/"):
        value = value.removeprefix("https://t.me/")
    elif value.startswith("http://t.me/"):
        value = value.removeprefix("http://t.me/")
    return value.lstrip("@/")


def build_public_channel_post_url(channel_username: str, message_id: int) -> str:
    return f"https://t.me/{_public_channel_username(channel_username)}/{message_id}"


def channel_upload_caption(result: DownloadResult, *, part_index: int | None = None, total_parts: int | None = None) -> str:
    caption = f"🎬 <b>{result.title or 'Download'}</b>"
    if part_index is not None and total_parts is not None and total_parts > 1:
        caption += f"\n📦 Part {part_index}/{total_parts}"
    if result.duration:
        caption += f"\n⏱ {format_duration(result.duration)}"
    if result.file_size:
        caption += f"\n💾 {format_size(result.file_size)}"
    return caption


def _channel_split_target_mb() -> int:
    configured_mb = max(1, config.MAX_FILE_SIZE // (1024 * 1024))
    return max(1, configured_mb - 5)


def _build_channel_post_urls(channel_username: str, message_ids: list[int]) -> list[str]:
    return [build_public_channel_post_url(channel_username, message_id) for message_id in message_ids]


def _channel_request_timeout(file_size: int | None) -> int:
    if not file_size:
        return 300
    return max(300, int(file_size / (1024 * 1024)) * 12)


def _cleanup_paths(paths: list[str]):
    for path in paths:
        cleanup_file(path)


async def _upload_media_to_channel(bot: Bot, result: DownloadResult, channel_chat_id: int | str, *, part_index: int | None = None, total_parts: int | None = None):
    file = FSInputFile(result.file_path or "")
    caption = channel_upload_caption(result, part_index=part_index, total_parts=total_parts)
    request_timeout = _channel_request_timeout(result.file_size)
    if result.file_path and result.file_path.lower().endswith((".m4a", ".mp3")):
        return await bot.send_audio(
            chat_id=channel_chat_id,
            audio=file,
            caption=caption,
            parse_mode="HTML",
            request_timeout=request_timeout,
        )
    return await bot.send_video(
        chat_id=channel_chat_id,
        video=file,
        caption=caption,
        parse_mode="HTML",
        supports_streaming=True,
        request_timeout=request_timeout,
    )


async def _resolve_admin_upload_channel(bot: Bot) -> ChatFullInfo:
    return await bot.get_chat(config.ADMIN_UPLOAD_CHANNEL)


async def _publish_direct_link_result(bot: Bot, status_msg, user_id: int, chat_id: int, url: str, platform: str, result: DownloadResult):
    published = await publish_direct_link(
        result.file_path or "",
        user_id=user_id,
        platform=platform,
        title=result.title or "Download",
        file_size=result.file_size or 0,
    )
    result.file_path = published.file_path

    caption = (
        f"🔗 <b>Your single-file link is ready</b>\n"
        f"🎬 <b>{result.title or 'Download'}</b>\n"
    )
    if result.duration:
        caption += f"⏱ {format_duration(result.duration)}\n"
    caption += (
        f"💾 {format_size(result.file_size or 0)}\n"
        f"⏳ Expires in {config.DIRECT_LINK_TTL_HOURS}h\n"
        f"🌐 {published.url}"
    )

    await record_download(user_id, url, platform, result.title or "Download", result.file_size or 0)
    await status_msg.edit_text(caption, parse_mode="HTML", disable_web_page_preview=True)

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
        await message.answer("❌ I couldn't recognize that link.\nSupported: YouTube, Facebook, Instagram, TikTok")
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
        if platform == "instagram":
            await loading.edit_text(
                "🔒 <b>Can't access this content</b>\n\n"
                "This might be because:\n"
                "• The account is <b>private</b> (bot doesn't follow them)\n"
                "• The story has <b>expired</b> (stories last 24h)\n"
                "• The post was <b>deleted</b>\n\n"
                "💡 If it's a private account, the bot needs to follow them first.",
                parse_mode="HTML",
            )
        else:
            await loading.edit_text("❌ Couldn't fetch this content. It might be private, expired, or temporarily unavailable.")
        return

    title = info.get("title", "Unknown")[:80]
    duration = info.get("duration")
    uploader = info.get("uploader", "")
    short_id = store_url(url, platform)

    if is_large_or_long(info):
        await loading.edit_text(
            direct_link_offer_text(title, duration, is_admin_user(user_id)),
            parse_mode="HTML",
            reply_markup=direct_link_keyboard(short_id, is_admin=is_admin_user(user_id)),
            disable_web_page_preview=True,
        )
        return

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
        reply_markup=quality_keyboard(short_id, platform),
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
    chat_id = callback.message.chat.id if callback.message else user_id
    await process_quality_download(bot, user_id, quality, short_id, chat_id, callback.message)


@router.callback_query(F.data.startswith("lk:"))
async def process_direct_link_callback(callback: CallbackQuery, bot: Bot):
    callback_data = callback.data or ""
    parts = callback_data.split(":", 2)
    if len(parts) < 3:
        await callback.answer("Invalid request")
        return

    short_id = parts[2]
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id if callback.message else user_id

    if is_admin_user(user_id):
        await callback.answer()
        await process_direct_link_download(bot, user_id, short_id, chat_id, callback.message)
        return

    await callback.answer("Please complete the Stars payment to generate the single-file link.")


@router.callback_query(F.data.startswith("ch:"))
async def process_channel_upload_callback(callback: CallbackQuery, bot: Bot):
    callback_data = callback.data or ""
    parts = callback_data.split(":", 2)
    if len(parts) < 3:
        await callback.answer("Invalid request")
        return

    short_id = parts[2]
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id if callback.message else user_id

    if not is_admin_user(user_id):
        await callback.answer("Admin only", show_alert=True)
        return

    await callback.answer()
    await process_channel_upload(bot, user_id, short_id, chat_id, callback.message)


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
    if quality not in ("audio", "720", "1080", "4k"):
        ok, err = await can_download(user_id)
        if not ok:
            if edit_msg:
                await edit_msg.edit_text(err)
            else:
                await bot.send_message(chat_id, err)
            return

    # Start download
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

    if result.file_size and result.file_size > config.MAX_FILE_SIZE:
        cleanup_file(result.file_path or "")
        await status_msg.edit_text(
            direct_link_offer_text(result.title or "Video", result.duration, is_admin_user(user_id)),
            parse_mode="HTML",
            reply_markup=direct_link_keyboard(short_id, is_admin=is_admin_user(user_id)),
            disable_web_page_preview=True,
        )
        return

    # Send file
    await status_msg.edit_text("📤 Uploading to Telegram...", parse_mode="HTML")

    try:
        caption = f"🎬 <b>{result.title}</b>"
        if result.duration:
            caption += f"\n⏱ {format_duration(result.duration)}"
        caption += f"\n💾 {format_size(result.file_size or 0)}"

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

        await record_download(user_id, url, platform, result.title or "Download", result.file_size or 0)
        await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text(f"❌ Upload failed: {str(e)[:100]}")
    finally:
        cleanup_file(result.file_path or "")


async def process_channel_upload(bot: Bot, user_id: int, short_id: str, chat_id: int, edit_msg=None):
    url_data = get_url(short_id)
    if not url_data:
        msg = "❌ Link expired. Please send the URL again."
        if edit_msg:
            await edit_msg.edit_text(msg)
        else:
            await bot.send_message(chat_id, msg)
        return
    url, platform = url_data

    if edit_msg:
        status_msg = await edit_msg.edit_text(
            f"📢 <b>Uploading to {config.ADMIN_UPLOAD_CHANNEL}...</b>\n⏳ This may take a few minutes\n\n❌ /cancel to abort",
            parse_mode="HTML",
        )
    else:
        status_msg = await bot.send_message(
            chat_id,
            f"📢 <b>Uploading to {config.ADMIN_UPLOAD_CHANNEL}...</b>\n⏳ This may take a few minutes\n\n❌ /cancel to abort",
            parse_mode="HTML",
        )

    async def do_download():
        return await download(url, platform, audio_only=False, quality="best")

    task = asyncio.create_task(do_download())
    set_active(user_id, task)

    try:
        result = await task
    except asyncio.CancelledError:
        await status_msg.edit_text("❌ Upload cancelled.")
        return
    finally:
        clear_active(user_id)

    if not result.success:
        error_text = result.error[:150] if result.error else "Unknown error"
        await status_msg.edit_text(f"❌ Download failed:\n<code>{error_text}</code>", parse_mode="HTML")
        return

    if result.file_size and result.file_size > config.PREMIUM_FILE_SIZE:
        cleanup_file(result.file_path or "")
        await status_msg.edit_text(
            f"❌ File is too large for Telegram channel upload ({format_size(result.file_size)}). Use the direct-link option instead.",
            parse_mode="HTML",
        )
        return

    try:
        channel_chat = await _resolve_admin_upload_channel(bot)
        channel_ref = channel_chat.username or _public_channel_username(config.ADMIN_UPLOAD_CHANNEL)

        if result.file_size and result.file_size > config.MAX_FILE_SIZE and result.file_path and result.file_path.lower().endswith('.mp4'):
            parts = split_video(result.file_path, max_size_mb=_channel_split_target_mb())
            uploaded_messages = []
            total_parts = len(parts)
            try:
                for idx, part_path in enumerate(parts, start=1):
                    part_result = DownloadResult(
                        success=True,
                        file_path=part_path,
                        title=result.title,
                        duration=result.duration,
                        file_size=os.path.getsize(part_path),
                        thumbnail=result.thumbnail,
                        platform=result.platform,
                    )
                    uploaded_messages.append(
                        await _upload_media_to_channel(
                            bot,
                            part_result,
                            channel_chat.id,
                            part_index=idx,
                            total_parts=total_parts,
                        )
                    )
                await record_download(user_id, url, platform, result.title or "Download", result.file_size or 0)
                urls = _build_channel_post_urls(channel_ref, [msg.message_id for msg in uploaded_messages])
                lines = "\n".join(f"• {post_url}" for post_url in urls)
                await status_msg.edit_text(
                    (
                        f"✅ <b>Uploaded to channel in {total_parts} parts</b>\n"
                        f"📢 <b>{getattr(channel_chat, 'title', channel_ref)}</b>\n"
                        f"🌐 Posts:\n{lines}"
                    ),
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
            finally:
                _cleanup_paths(parts)
                cleanup_file(result.file_path or "")
            return

        if result.file_size and result.file_size > config.MAX_FILE_SIZE:
            cleanup_file(result.file_path or "")
            await status_msg.edit_text(
                f"❌ File is too large for direct bot upload ({format_size(result.file_size)}). Use the direct-link option instead.",
                parse_mode="HTML",
            )
            return

        message = await _upload_media_to_channel(bot, result, channel_chat.id)
        post_url = build_public_channel_post_url(channel_ref, message.message_id)
        await record_download(user_id, url, platform, result.title or "Download", result.file_size or 0)
        await status_msg.edit_text(
            (
                f"✅ <b>Uploaded to channel</b>\n"
                f"📢 <b>{getattr(channel_chat, 'title', channel_ref)}</b>\n"
                f"🌐 {post_url}"
            ),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception as e:
        await status_msg.edit_text(
            f"❌ Channel upload failed: <code>{str(e)[:180]}</code>\n\nTry the direct-link option instead.",
            parse_mode="HTML",
        )
    finally:
        cleanup_file(result.file_path or "")


async def process_direct_link_download(bot: Bot, user_id: int, short_id: str, chat_id: int, edit_msg=None):
    url_data = get_url(short_id)
    if not url_data:
        msg = "❌ Link expired. Please send the URL again."
        if edit_msg:
            await edit_msg.edit_text(msg)
        else:
            await bot.send_message(chat_id, msg)
        return
    url, platform = url_data

    if edit_msg:
        status_msg = await edit_msg.edit_text(
            "🔗 <b>Preparing single-file link...</b>\n⏳ This may take a few minutes\n\n❌ /cancel to abort",
            parse_mode="HTML",
        )
    else:
        status_msg = await bot.send_message(
            chat_id,
            "🔗 <b>Preparing single-file link...</b>\n⏳ This may take a few minutes\n\n❌ /cancel to abort",
            parse_mode="HTML",
        )

    async def do_download():
        return await download(url, platform, audio_only=False, quality="best")

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

    try:
        await _publish_direct_link_result(bot, status_msg, user_id, chat_id, url, platform, result)
    except Exception as e:
        cleanup_file(result.file_path or "")
        await status_msg.edit_text(
            f"❌ Failed to create direct link: <code>{str(e)[:150]}</code>",
            parse_mode="HTML",
        )

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
