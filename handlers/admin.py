from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from database.db import get_stats, ban_user, get_or_create_user
from config import config

router = Router()

def is_admin(user_id: int) -> bool:
    return user_id == config.ADMIN_ID

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    stats = await get_stats()
    await message.answer(
        f"🔧 <b>Admin Dashboard</b>\n\n"
        f"👥 Total users: {stats['total_users']}\n"
        f"📥 Today's downloads: {stats['today_downloads']}\n"
        f"📊 All-time downloads: {stats['total_downloads']}\n\n"
        f"Commands:\n"
        f"/ban <user_id> — Ban user\n"
        f"/unban <user_id> — Unban user",
        parse_mode="HTML",
    )

@router.message(Command("ban"))
async def cmd_ban(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Usage: /ban <user_id>")
        return
    try:
        target = int(parts[1])
        await ban_user(target, True)
        await message.answer(f"🚫 User {target} banned.")
    except ValueError:
        await message.answer("Invalid user ID.")

@router.message(Command("unban"))
async def cmd_unban(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Usage: /unban <user_id>")
        return
    try:
        target = int(parts[1])
        await ban_user(target, False)
        await message.answer(f"✅ User {target} unbanned.")
    except ValueError:
        await message.answer("Invalid user ID.")
