from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from database.db import (
    get_stats, ban_user, get_or_create_user, get_all_users,
    get_recent_downloads, get_user_by_id, set_user_limit, get_daily_stats
)
from config import config

router = Router()

def is_admin(user_id: int) -> bool:
    return user_id == config.ADMIN_ID

def admin_only(func):
    async def wrapper(message: Message, **kwargs):
        if not is_admin(message.from_user.id):
            return
        return await func(message, **kwargs)
    return wrapper

# ─── Main Admin Panel ───────────────────────────────────────
@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    stats = await get_stats()
    text = (
        f"🔧 <b>Admin Dashboard</b>\n\n"
        f"👥 Total users: <b>{stats['total_users']}</b>\n"
        f"📥 Today's downloads: <b>{stats['today_downloads']}</b>\n"
        f"📊 All-time downloads: <b>{stats['total_downloads']}</b>\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👥 Users", callback_data="adm:users:0"),
            InlineKeyboardButton(text="📥 Downloads", callback_data="adm:dl:0"),
        ],
        [
            InlineKeyboardButton(text="📊 Stats", callback_data="adm:stats"),
            InlineKeyboardButton(text="📢 Broadcast", callback_data="adm:broadcast"),
        ],
        [
            InlineKeyboardButton(text="🔍 Find User", callback_data="adm:find"),
        ],
    ])
    await message.answer(text, parse_mode="HTML", reply_markup=kb)

# ─── Callback Router ────────────────────────────────────────
@router.callback_query(F.data.startswith("adm:"))
async def admin_callbacks(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Not authorized", show_alert=True)
        return

    parts = callback.data.split(":")
    action = parts[1]

    if action == "users":
        await show_users(callback, int(parts[2]) if len(parts) > 2 else 0)
    elif action == "dl":
        await show_downloads(callback, int(parts[2]) if len(parts) > 2 else 0)
    elif action == "stats":
        await show_stats(callback)
    elif action == "ban":
        await toggle_ban(callback, int(parts[2]), True)
    elif action == "unban":
        await toggle_ban(callback, int(parts[2]), False)
    elif action == "limit":
        await show_limit_menu(callback, int(parts[2]))
    elif action == "setlimit":
        await set_limit(callback, int(parts[2]), int(parts[3]))
    elif action == "userinfo":
        await show_user_info(callback, int(parts[2]))
    elif action == "find":
        await callback.answer("Send /find <user_id> or @username", show_alert=True)
    elif action == "broadcast":
        await callback.answer("Send /broadcast <message>", show_alert=True)
    elif action == "back":
        await callback.message.delete()
        await cmd_admin(callback.message)
    await callback.answer()

# ─── Users List ─────────────────────────────────────────────
async def show_users(callback: CallbackQuery, page: int = 0):
    users = await get_all_users()
    per_page = 8
    total_pages = max(1, (len(users) + per_page - 1) // per_page)
    page = min(page, total_pages - 1)
    start = page * per_page
    chunk = users[start:start + per_page]

    lines = ["👥 <b>Users</b>\n"]
    for u in chunk:
        ban_icon = "🚫" if u["is_banned"] else "✅"
        name = u["first_name"] or u["username"] or str(u["user_id"])
        lines.append(f"{ban_icon} <code>{u['user_id']}</code> — {name} ({u['downloads_today']} today)")

    text = "\n".join(lines) + f"\n\nPage {page + 1}/{total_pages} — {len(users)} total"
    kb = user_buttons(chunk, page, total_pages, "users")
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

# ─── Recent Downloads ───────────────────────────────────────
async def show_downloads(callback: CallbackQuery, page: int = 0):
    downloads = await get_recent_downloads(50)
    per_page = 6
    total_pages = max(1, (len(downloads) + per_page - 1) // per_page)
    page = min(page, total_pages - 1)
    start = page * per_page
    chunk = downloads[start:start + per_page]

    lines = ["📥 <b>Recent Downloads</b>\n"]
    for d in chunk:
        platform_icon = {"youtube": "🔴", "instagram": "📸", "tiktok": "🎵"}.get(d["platform"], "🌐")
        title = (d["title"] or "Unknown")[:35]
        size = f"{d['file_size'] / 1024 / 1024:.1f}MB" if d["file_size"] else "N/A"
        lines.append(f"{platform_icon} <code>{d['user_id']}</code> — {title} ({size})")

    text = "\n".join(lines) + f"\n\nPage {page + 1}/{total_pages}"
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"adm:dl:{page-1}"))
    buttons.append(InlineKeyboardButton(text="🔙 Back", callback_data="adm:back"))
    if page < total_pages - 1:
        buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"adm:dl:{page+1}"))
    kb = InlineKeyboardMarkup(inline_keyboard=[buttons] if buttons else [])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

# ─── Stats ──────────────────────────────────────────────────
async def show_stats(callback: CallbackQuery):
    stats = await get_stats()
    daily = await get_daily_stats(7)

    text = (
        f"📊 <b>Statistics</b>\n\n"
        f"👥 Total users: <b>{stats['total_users']}</b>\n"
        f"📥 Total downloads: <b>{stats['total_downloads']}</b>\n"
        f"📅 Today: <b>{stats['today_downloads']}</b>\n"
    )

    if daily:
        text += "\n📈 <b>Last 7 days:</b>\n"
        for day in daily:
            text += f"  {day['date']}: {day['total_downloads']} downloads\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back", callback_data="adm:back")]
    ])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

# ─── User Info ──────────────────────────────────────────────
async def show_user_info(callback: CallbackQuery, user_id: int):
    user = await get_user_by_id(user_id)
    if not user:
        await callback.answer("User not found", show_alert=True)
        return

    ban_status = "🚫 BANNED" if user["is_banned"] else "✅ Active"
    limit = user["daily_limit"] if user["daily_limit"] != 0 else "Unlimited"
    text = (
        f"👤 <b>User Info</b>\n\n"
        f"ID: <code>{user['user_id']}</code>\n"
        f"Name: {user['first_name'] or 'N/A'}\n"
        f"Username: @{user['username'] or 'N/A'}\n"
        f"Status: {ban_status}\n"
        f"Downloads today: {user['downloads_today']}\n"
        f"Daily limit: {limit}\n"
        f"Extra downloads: {user['extra_downloads']}\n"
        f"Joined: {user['created_at']}\n"
    )
    ban_text = "✅ Unban" if user["is_banned"] else "🚫 Ban"
    ban_action = f"adm:unban:{user_id}" if user["is_banned"] else f"adm:ban:{user_id}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=ban_text, callback_data=ban_action),
            InlineKeyboardButton(text="📏 Set Limit", callback_data=f"adm:limit:{user_id}"),
        ],
        [InlineKeyboardButton(text="🔙 Back", callback_data="adm:users:0")],
    ])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

# ─── Ban/Unban ──────────────────────────────────────────────
async def toggle_ban(callback: CallbackQuery, user_id: int, ban: bool):
    await ban_user(user_id, ban)
    status = "banned 🚫" if ban else "unbanned ✅"
    await callback.answer(f"User {user_id} {status}")
    await show_user_info(callback, user_id)

# ─── Limit Menu ─────────────────────────────────────────────
async def show_limit_menu(callback: CallbackQuery, user_id: int):
    text = f"📏 Set daily limit for <code>{user_id}</code>"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="10", callback_data=f"adm:setlimit:{user_id}:10"),
            InlineKeyboardButton(text="20", callback_data=f"adm:setlimit:{user_id}:20"),
            InlineKeyboardButton(text="50", callback_data=f"adm:setlimit:{user_id}:50"),
        ],
        [
            InlineKeyboardButton(text="100", callback_data=f"adm:setlimit:{user_id}:100"),
            InlineKeyboardButton(text="∞ Unlimited", callback_data=f"adm:setlimit:{user_id}:0"),
        ],
        [InlineKeyboardButton(text="🔙 Back", callback_data=f"adm:userinfo:{user_id}")],
    ])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

async def set_limit(callback: CallbackQuery, user_id: int, limit: int):
    await set_user_limit(user_id, limit)
    label = "unlimited" if limit == 0 else f"{limit}/day"
    await callback.answer(f"Limit set to {label}")
    await show_user_info(callback, user_id)

# ─── Helper: User action buttons ────────────────────────────
def user_buttons(users, page, total_pages, prefix):
    rows = []
    for u in users:
        name = u["first_name"] or u["username"] or str(u["user_id"])[:8]
        rows.append([InlineKeyboardButton(
            text=f"👤 {name}",
            callback_data=f"adm:userinfo:{u['user_id']}"
        )])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"adm:{prefix}:{page-1}"))
    nav.append(InlineKeyboardButton(text="🔙", callback_data="adm:back"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"adm:{prefix}:{page+1}"))
    rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ─── /find command ──────────────────────────────────────────
@router.message(Command("find"))
async def cmd_find(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: /find <user_id> or @username")
        return
    query = parts[1].strip().lstrip("@")

    try:
        user_id = int(query)
        user = await get_user_by_id(user_id)
    except ValueError:
        await message.answer("Please provide a numeric user ID")
        return

    if not user:
        await message.answer("User not found.")
        return

    ban_status = "🚫 BANNED" if user["is_banned"] else "✅ Active"
    limit = user["daily_limit"] if user["daily_limit"] != 0 else "Unlimited"
    text = (
        f"👤 <b>User Found</b>\n\n"
        f"ID: <code>{user['user_id']}</code>\n"
        f"Name: {user['first_name'] or 'N/A'}\n"
        f"Username: @{user['username'] or 'N/A'}\n"
        f"Status: {ban_status}\n"
        f"Downloads today: {user['downloads_today']}\n"
        f"Daily limit: {limit}\n"
        f"Extra: {user['extra_downloads']}\n"
    )
    ban_text = "✅ Unban" if user["is_banned"] else "🚫 Ban"
    ban_action = f"adm:unban:{user_id}" if user["is_banned"] else f"adm:ban:{user_id}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=ban_text, callback_data=ban_action),
            InlineKeyboardButton(text="📏 Set Limit", callback_data=f"adm:limit:{user_id}"),
        ],
    ])
    await message.answer(text, parse_mode="HTML", reply_markup=kb)

# ─── /broadcast command ─────────────────────────────────────
@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: /broadcast <message>")
        return

    text = parts[1]
    users = await get_all_users()
    sent, failed = 0, 0

    status_msg = await message.answer(f"📢 Broadcasting to {len(users)} users...")

    for u in users:
        try:
            await message.bot.send_message(u["user_id"], text)
            sent += 1
        except Exception:
            failed += 1

    await status_msg.edit_text(f"📢 Broadcast complete!\n✅ Sent: {sent}\n❌ Failed: {failed}")
