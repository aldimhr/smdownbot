from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery, LabeledPrice, PreCheckoutQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.filters import Command
from database.db import add_extra_downloads, get_or_create_user
from config import config

router = Router()

# In-memory store for pending premium downloads
# Key: f"premium_{user_id}", Value: (quality, short_id)
_pending_downloads: dict[str, tuple[str, str]] = {}

QUALITY_PRICES = {
    "audio": config.STARS_AUDIO,
    "720": config.STARS_720P,
    "1080": config.STARS_1080P,
    "4k": config.STARS_4K,
}

QUALITY_LABELS = {
    "audio": "Audio MP3",
    "720": "720p HD",
    "1080": "1080p Full HD",
    "4k": "4K Best Quality",
}


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


# ─── Premium quality callback (pm:quality:short_id) ─────────
@router.callback_query(F.data.startswith("pm:"))
async def premium_quality_callback(callback: CallbackQuery, bot: Bot):
    parts = callback.data.split(":", 2)
    if len(parts) < 3:
        await callback.answer("Invalid request")
        return

    quality = parts[1]
    short_id = parts[2]
    price = QUALITY_PRICES.get(quality)
    label = QUALITY_LABELS.get(quality, quality)

    if not price:
        await callback.answer("Unknown quality")
        return

    user_id = callback.from_user.id

    # Store pending download
    _pending_downloads[f"premium_{user_id}"] = (quality, short_id)

    await bot.send_invoice(
        chat_id=user_id,
        title=f"{label} Download",
        description=f"Download video in {label} quality",
        payload=f"premium_{quality}_{user_id}",
        currency="XTR",
        prices=[LabeledPrice(label=label, amount=price)],
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
    payload = payment.invoice_payload

    if payload.startswith("extra_downloads_"):
        # Extra downloads purchase
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

    elif payload.startswith("premium_"):
        # Premium quality download — trigger the download automatically
        pending_key = f"premium_{user_id}"
        pending = _pending_downloads.pop(pending_key, None)

        if not pending:
            await message.answer(
                f"✅ Payment received ({payment.total_amount} Stars)!\n\n"
                f"⚠️ Download info expired. Please send the link again.",
                parse_mode="HTML",
            )
            return

        quality, short_id = pending
        label = QUALITY_LABELS.get(quality, quality)

        await message.answer(
            f"✅ <b>Payment successful!</b>\n\n"
            f"🎬 Quality: <b>{label}</b>\n"
            f"💰 Paid: <b>{payment.total_amount}</b> Stars\n\n"
            f"📥 Starting download...",
            parse_mode="HTML",
        )

        # Trigger the download by simulating the dl: callback
        # We need to import and call the download logic directly
        from handlers.download import process_quality_download
        await process_quality_download(message.bot, user_id, quality, short_id, message.chat.id)
