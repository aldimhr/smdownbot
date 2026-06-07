from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery, LabeledPrice, PreCheckoutQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.filters import Command
from database.db import add_extra_downloads, get_or_create_user
from config import config

router = Router()

# ─── /buy command ───────────────────────────────────────────
@router.message(Command("buy"))
async def cmd_buy(message: Message):
    user = await get_or_create_user(message.from_user.id)
    extra = user.get("extra_downloads", 0)

    text = (
        f"⭐ <b>Extra Downloads</b>\n\n"
        f"🎁 Your extra downloads: <b>{extra}</b>\n\n"
        f"Get <b>{config.STARS_EXTRA_DOWNLOADS}</b> extra downloads for today!\n"
        f"Price: <b>{config.STARS_PRICE}</b> Telegram Stars\n\n"
        f"Tap below to purchase:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"⭐ Buy {config.STARS_EXTRA_DOWNLOADS} downloads — {config.STARS_PRICE} Stars",
            callback_data="buy_stars"
        )]
    ])
    await message.answer(text, parse_mode="HTML", reply_markup=kb)

# ─── Buy button callback ────────────────────────────────────
@router.callback_query(F.data == "buy_stars")
async def buy_stars_callback(callback: CallbackQuery, bot: Bot):
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title="Extra Downloads",
        description=f"{config.STARS_EXTRA_DOWNLOADS} extra downloads for today",
        payload=f"extra_downloads_{callback.from_user.id}",
        currency="XTR",  # Telegram Stars currency
        prices=[LabeledPrice(label="Extra Downloads", amount=config.STARS_PRICE)],
    )
    await callback.answer()

# ─── Pre-checkout (required by Telegram) ────────────────────
@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout: PreCheckoutQuery, bot: Bot):
    await bot.answer_pre_checkout_query(pre_checkout.id, ok=True)

# ─── Successful payment ─────────────────────────────────────
@router.message(F.successful_payment)
async def process_successful_payment(message: Message):
    payment = message.successful_payment
    user_id = message.from_user.id

    await add_extra_downloads(user_id, config.STARS_EXTRA_DOWNLOADS)

    user = await get_or_create_user(user_id)
    extra = user.get("extra_downloads", 0)

    await message.answer(
        f"✅ <b>Payment successful!</b>\n\n"
        f"🎁 Added <b>{config.STARS_EXTRA_DOWNLOADS}</b> extra downloads\n"
        f"💰 Paid: <b>{payment.total_amount}</b> Stars\n\n"
        f"Your extra downloads: <b>{extra}</b>\n"
        f"Send me a link to download! 🚀",
        parse_mode="HTML",
    )
