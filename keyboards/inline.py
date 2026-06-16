from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import config


def quality_keyboard(short_id: str, platform: str) -> InlineKeyboardMarkup:
    buttons = []
    if platform in ("youtube", "unknown"):
        buttons.append([
            InlineKeyboardButton(text="📱 480p (Free)", callback_data=f"dl:480:{short_id}"),
        ])
        buttons.append([
            InlineKeyboardButton(text="🎵 Audio MP3 ⭐2", callback_data=f"pm:audio:{short_id}"),
            InlineKeyboardButton(text="🎬 720p ⭐3", callback_data=f"pm:720:{short_id}"),
        ])
        buttons.append([
            InlineKeyboardButton(text="🔥 1080p ⭐5", callback_data=f"pm:1080:{short_id}"),
            InlineKeyboardButton(text="⭐ 4K Best ⭐10", callback_data=f"pm:4k:{short_id}"),
        ])
    elif platform == "tiktok":
        buttons.append([
            InlineKeyboardButton(text="🎬 Video", callback_data=f"dl:best:{short_id}"),
            InlineKeyboardButton(text="🎵 Audio Only", callback_data=f"dl:audio:{short_id}"),
        ])
    elif platform in ("instagram", "facebook"):
        buttons.append([
            InlineKeyboardButton(text="📥 Download", callback_data=f"dl:best:{short_id}"),
        ])
    buttons.append([
        InlineKeyboardButton(text="❌ Cancel", callback_data="cancel"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def direct_link_keyboard(short_id: str, is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = []
    if is_admin:
        rows.append([
            InlineKeyboardButton(text="🔗 Generate single-file link", callback_data=f"lk:best:{short_id}"),
        ])
        rows.append([
            InlineKeyboardButton(text="📢 Upload to @stokdramacina", callback_data=f"ch:best:{short_id}"),
        ])
    else:
        rows.append([
            InlineKeyboardButton(text=f"🔗 Single-file link ⭐{config.STARS_DIRECT_LINK}", callback_data=f"lk:best:{short_id}"),
        ])
    rows.append([
        InlineKeyboardButton(text="❌ Cancel", callback_data="cancel"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Cancel Download", callback_data="cancel")]
    ])


def buy_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"⭐ Buy {config.STARS_EXTRA_DOWNLOADS} extra downloads",
            callback_data="buy_stars"
        )]
    ])
