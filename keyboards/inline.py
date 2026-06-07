from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def quality_keyboard(short_id: str, platform: str) -> InlineKeyboardMarkup:
    buttons = []
    if platform in ("youtube", "unknown"):
        buttons.append([
            InlineKeyboardButton(text="🎬 720p", callback_data=f"dl:720:{short_id}"),
            InlineKeyboardButton(text="📱 480p", callback_data=f"dl:480:{short_id}"),
        ])
        buttons.append([
            InlineKeyboardButton(text="🎵 Audio MP3", callback_data=f"dl:audio:{short_id}"),
            InlineKeyboardButton(text="🎬 Best Quality", callback_data=f"dl:best:{short_id}"),
        ])
    elif platform == "tiktok":
        buttons.append([
            InlineKeyboardButton(text="🎬 Video", callback_data=f"dl:best:{short_id}"),
            InlineKeyboardButton(text="🎵 Audio Only", callback_data=f"dl:audio:{short_id}"),
        ])
    elif platform == "instagram":
        buttons.append([
            InlineKeyboardButton(text="📥 Download", callback_data=f"dl:best:{short_id}"),
        ])
    buttons.append([
        InlineKeyboardButton(text="❌ Cancel", callback_data="cancel"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Cancel Download", callback_data="cancel")]
    ])

def buy_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="⭐ Buy 10 extra downloads",
            callback_data="buy_stars"
        )]
    ])
