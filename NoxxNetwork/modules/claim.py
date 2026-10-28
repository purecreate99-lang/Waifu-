"""
Claim Command — /claim to get 500 Edollers.
Resets at Midnight (12:00 AM IST).
Only works in MAIN_CHAT_ID.
"""
from datetime import datetime, timezone, timedelta
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from NoxxNetwork import application, db, LOGGER, MAIN_CHAT_ID
from NoxxNetwork.modules.coin import (
    add_coins,
    get_balance,
    CURRENCY,
    CURRENCY_SYMBOL,
    _fmt,
)

# Config
CLAIM_AMOUNT = 500
coins_collection = db['user_coins']

# IST Timezone (UTC + 5:30)
IST = timezone(timedelta(hours=5, minutes=30))


async def claim(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id

    # 🚫 Only allow in MAIN_CHAT_ID
    if chat_id != MAIN_CHAT_ID:
        await update.message.reply_text("⚠️ Please use /claim only in the Main chat!")
        return

    user = update.effective_user
    user_id = user.id

    # Current time in IST
    now_ist = datetime.now(IST)
    today_date = now_ist.strftime("%Y-%m-%d")  # e.g., "2026-10-28"

    # Fetch user data
    doc = await coins_collection.find_one({'user_id': user_id}) or {}
    last_claim_date = doc.get('last_claim_date')

    # Check if already claimed today
    if last_claim_date == today_date:
        # Calculate time left until midnight
        tomorrow = (now_ist + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        time_left = tomorrow - now_ist
        hours = time_left.seconds // 3600
        minutes = (time_left.seconds % 3600) // 60

        await update.message.reply_text(
            f"⏳ <b>You have already claimed your daily reward!</b>\n"
            f"Come back in <b>{hours}h {minutes}m {seconds}s</b>.",
            parse_mode='HTML'
        )
        return

    # Add coins
    await add_coins(user_id, CLAIM_AMOUNT)
    new_balance = await get_balance(user_id)

    # Update last claim date
    await coins_collection.update_one(
        {'user_id': user_id},
        {'$set': {'last_claim_date': today_date}},
        upsert=True
    )

    await update.message.reply_text(
        f"🎁 <b>𝐃ᴀɪʟʏ 𝐑ᴇᴡᴀʀᴅ 𝐂ʟᴀɪᴍᴇᴅ!</b>\n"
        f"💰 <b>𝐑ᴇᴄᴇɪᴠᴇᴅ:</b> {CURRENCY_SYMBOL}{_fmt(CLAIM_AMOUNT)} {CURRENCY}",
        parse_mode='HTML'
    )


# Register Handler
application.add_handler(CommandHandler("claim", claim, block=False))
