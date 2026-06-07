from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def quality_keyboard(url: str, platform: str) -> InlineKeyboardMarkup:
    buttons = []
    if platform in ("youtube", "unknown"):
        buttons.append([
            InlineKeyboardButton(text="🎬 720p", callback_data=f"dl:720:{url[:60]}"),
            InlineKeyboardButton(text="📱 480p", callback_data=f"dl:480:{url[:60]}"),
        ])
        buttons.append([
            InlineKeyboardButton(text="🎵 Audio MP3", callback_data=f"dl:audio:{url[:60]}"),
            InlineKeyboardButton(text="🎬 Best Quality", callback_data=f"dl:best:{url[:60]}"),
        ])
    elif platform == "tiktok":
        buttons.append([
            InlineKeyboardButton(text="🎬 Video", callback_data=f"dl:best:{url[:60]}"),
            InlineKeyboardButton(text="🎵 Audio Only", callback_data=f"dl:audio:{url[:60]}"),
        ])
    elif platform == "instagram":
        buttons.append([
            InlineKeyboardButton(text="📥 Download", callback_data=f"dl:best:{url[:60]}"),
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
            text=f"⭐ Buy 10 extra downloads",
            callback_data="buy_stars"
        )]
    ])

def share_inline_keyboard(query_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Share in chat", switch_inline_query="")]
    ])
