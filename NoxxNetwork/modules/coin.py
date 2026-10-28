
import asyncio
import random
import time
from html import escape

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext

from NoxxNetwork import (
    application,
    user_collection,
    db,
    OWNER_ID,
    sudo_users,
    SUPPORT_CHAT,
    MAIN_CHAT_ID,
    LOGGER,
)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CURRENCY = "Waifu Edollers"
CURRENCY_SYMBOL = "$"

BALL_COOLDOWN = 40                          # seconds between balls
BALLS_PER_WINDOW = 6                        # balls per window
WINDOW_DURATION = 12 * 60 * 60              # 12 hours in seconds

coins_collection = db['user_coins']


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def get_balance(user_id: int) -> int:
    doc = await coins_collection.find_one({'user_id': user_id})
    return int(doc.get('coins', 0)) if doc else 0


async def add_coins(user_id: int, amount: int) -> int:
    if amount == 0:
        return await get_balance(user_id)
    doc = await coins_collection.find_one_and_update(
        {'user_id': user_id},
        {'$inc': {'coins': amount}},
        upsert=True,
        return_document=True,
    )
    return int(doc.get('coins', 0))


def _fmt(number: int) -> str:
    return f"{int(number):,}"


def _bar() -> str:
    return "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"


# ---------------------------------------------------------------------------
# /wpocket — show balance + balls left
# ---------------------------------------------------------------------------
async def wpocket(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    balance = await get_balance(user.id)

    # Calculate balls left
    doc = await coins_collection.find_one({'user_id': user.id}) or {}
    now = int(time.time())
    window_start = int(doc.get('window_start', 0))
    balls_used = int(doc.get('balls_used', 0))

    if now - window_start >= WINDOW_DURATION:
        balls_left = BALLS_PER_WINDOW
    else:
        balls_left = max(0, BALLS_PER_WINDOW - balls_used)

    name = escape(user.first_name or "User")
    username_line = f"@{user.username}" if user.username else name

    text = (
        f"<b>{name}, Here is Your Pocket Balance:</b>\n\n"
        f"{_bar()}\n"
        f"❄ <b>Pocket Of</b> <a href=\"tg://user?id={user.id}\">{username_line}</a>\n\n"
        f"💵 <b>Currency:</b>\n"
        f"❄ {CURRENCY} ➤ <b>{CURRENCY_SYMBOL}{_fmt(balance)}</b>\n\n"
        f"🎳 <b>Balls Left:</b> {balls_left}/{BALLS_PER_WINDOW}\n"
        f"{_bar()}"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 Sᴜᴘᴘᴏʀᴛ", url=f"https://t.me/{SUPPORT_CHAT}")],
    ])

    await update.message.reply_text(text, parse_mode='HTML', reply_markup=keyboard)


# ---------------------------------------------------------------------------
# /wsend <amount> (reply)
# ---------------------------------------------------------------------------
async def wsend(update: Update, context: CallbackContext) -> None:
    message = update.effective_message
    sender = update.effective_user

    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply_text("Rᴇᴘʟʏ ᴛᴏ ᴛʜᴇ ᴜsᴇʀ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ sᴇɴᴅ ᴄᴏɪɴs ᴛᴏ.")
        return

    receiver = message.reply_to_message.from_user
    receiver_id = receiver.id
    sender_id = sender.id

    if sender_id == receiver_id:
        await message.reply_text("Yᴏᴜ ᴄᴀɴ'ᴛ sᴇɴᴅ ᴄᴏɪɴs ᴛᴏ ʏᴏᴜʀsᴇʟғ! 😅")
        return

    if not context.args:
        await message.reply_text("U sᴀɢᴇ: /wsend <amount>\nExᴀᴍᴘʟᴇ: /wsend 500")
        return

    try:
        amount = int(context.args[0])
    except ValueError:
        await message.reply_text("Iɴᴠᴀʟɪᴅ ᴀᴍᴏᴜɴᴛ. Pʟᴇᴀsᴇ ᴇɴᴛᴇʀ ᴀ ᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀ.")
        return

    if amount <= 0:
        await message.reply_text("Aᴍᴏᴜɴᴛ ᴍᴜsᴛ ʙᴇ ɢʀᴇᴀᴛᴇʀ ᴛʜᴀɴ 0.")
        return

    if amount < 10:
        await message.reply_text("Mɪɴɪᴍᴜᴍ sᴇɴᴅ ᴀᴍᴏᴜɴᴛ ɪs <b>10</b>.", parse_mode='HTML')
        return

    sender_balance = await get_balance(sender_id)
    if sender_balance < amount:
        await message.reply_text(
            f"❌ <b>Iɴsᴜғғɪᴄɪᴇɴᴛ Bᴀʟᴀɴᴄᴇ</b>\n\n"
            f"Yᴏᴜʀ Bᴀʟᴀɴᴄᴇ: <b>{CURRENCY_SYMBOL}{_fmt(sender_balance)}</b>\n"
            f"Rᴇǫᴜɪʀᴇᴅ: <b>{CURRENCY_SYMBOL}{_fmt(amount)}</b>",
            parse_mode='HTML',
        )
        return

    await add_coins(sender_id, -amount)
    await add_coins(receiver_id, amount)

    sender_mention = f'<a href="tg://user?id={sender_id}">{escape(sender.first_name or "User")}</a>'
    receiver_mention = f'<a href="tg://user?id={receiver_id}">{escape(receiver.first_name or "User")}</a>'

    new_sender_balance = await get_balance(sender_id)

    await message.reply_text(
        f"✅ <b>Cᴏɪɴs Tʀᴀɴsғᴇʀʀᴇᴅ</b>\n\n"
        f"Fʀᴏᴍ: {sender_mention}\n"
        f"Tᴏ: {receiver_mention}\n"
        f"Aᴍᴏᴜɴᴛ: <b>{CURRENCY_SYMBOL}{_fmt(amount)}</b> {CURRENCY}\n\n"
        f"Yᴏᴜʀ ɴᴇᴡ ʙᴀʟᴀɴᴄᴇ: <b>{CURRENCY_SYMBOL}{_fmt(new_sender_balance)}</b>",
        parse_mode='HTML',
    )


# ---------------------------------------------------------------------------
# /wtop — top coin holders
# ---------------------------------------------------------------------------
async def wtop(update: Update, context: CallbackContext) -> None:
    cursor = coins_collection.find({'coins': {'$gt': 0}}).sort('coins', -1).limit(10)
    data = await cursor.to_list(length=10)

    if not data:
        await update.message.reply_text("Nᴏ ᴜsᴇʀs ʏᴇᴛ.")
        return

    medal = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = [f"🏆 <b>Tᴏᴘ {CURRENCY} Hᴏʟᴅᴇʀs</b>", "", _bar(), ""]

    for i, entry in enumerate(data, 1):
        uid = entry.get('user_id')
        coins = int(entry.get('coins', 0))
        try:
            user_doc = await user_collection.find_one({'id': uid})
            name = user_doc.get('first_name', f"User {uid}") if user_doc else f"User {uid}"
        except Exception:
            name = f"User {uid}"
        prefix = medal.get(i, f"{i}.")
        lines.append(f"{prefix} <b>{escape(str(name))}</b> — <b>{CURRENCY_SYMBOL}{_fmt(coins)}</b>")

    lines.append("")
    lines.append(_bar())

    await update.message.reply_text("\n".join(lines), parse_mode='HTML')


# ---------------------------------------------------------------------------
# /wadd <amount> (reply) — SUDO/OWNER only
# ---------------------------------------------------------------------------
async def wadd(update: Update, context: CallbackContext) -> None:
    message = update.effective_message
    caller_id = update.effective_user.id

    if str(caller_id) not in sudo_users and caller_id != OWNER_ID:
        await message.reply_text("⚠️ Oɴʟʏ Sᴜᴅᴏ Usᴇʀs ᴄᴀɴ ᴜsᴇ ᴛʜɪs.")
        return

    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply_text("Rᴇᴘʟʏ ᴛᴏ ᴀ ᴜsᴇʀ ᴛᴏ ᴀᴅᴅ ᴄᴏɪɴs.")
        return

    if not context.args:
        await message.reply_text("U sᴀɢᴇ: /wadd <amount>")
        return

    try:
        amount = int(context.args[0])
    except ValueError:
        await message.reply_text("Iɴᴠᴀʟɪᴅ ᴀᴍᴏᴜɴᴛ.")
        return

    target = message.reply_to_message.from_user
    await add_coins(target.id, amount)
    new_balance = await get_balance(target.id)

    await message.reply_text(
        f"✅ Aᴅᴅᴇᴅ <b>{CURRENCY_SYMBOL}{_fmt(amount)}</b> ᴛᴏ "
        f"<a href=\"tg://user?id={target.id}\">{escape(target.first_name or 'User')}</a>\n"
        f"Nᴇᴡ Bᴀʟᴀɴᴄᴇ: <b>{CURRENCY_SYMBOL}{_fmt(new_balance)}</b>",
        parse_mode='HTML',
    )


# ---------------------------------------------------------------------------
# /wremove <amount> (reply) — SUDO/OWNER only
# ---------------------------------------------------------------------------
async def wremove(update: Update, context: CallbackContext) -> None:
    message = update.effective_message
    caller_id = update.effective_user.id

    if str(caller_id) not in sudo_users and caller_id != OWNER_ID:
        await message.reply_text("⚠️ Oɴʟʏ Sᴜᴅᴏ Usᴇʀs ᴄᴀɴ ᴜsᴇ ᴛʜɪs.")
        return

    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply_text("Rᴇᴘʟʏ ᴛᴏ ᴀ ᴜsᴇʀ ᴛᴏ ʀᴇᴍᴏᴠᴇ ᴄᴏɪɴs.")
        return

    if not context.args:
        await message.reply_text("U sᴀɢᴇ: /wremove <amount>")
        return

    try:
        amount = int(context.args[0])
    except ValueError:
        await message.reply_text("Iɴᴠᴀʟɪᴅ ᴀᴍᴏᴜɴᴛ.")
        return

    target = message.reply_to_message.from_user
    await add_coins(target.id, -abs(amount))
    new_balance = await get_balance(target.id)

    await message.reply_text(
        f"✅ Rᴇᴍᴏᴠᴇᴅ <b>{CURRENCY_SYMBOL}{_fmt(abs(amount))}</b> ғʀᴏᴍ "
        f"<a href=\"tg://user?id={target.id}\">{escape(target.first_name or 'User')}</a>\n"
        f"Nᴇᴡ Bᴀʟᴀɴᴄᴇ: <b>{CURRENCY_SYMBOL}{_fmt(new_balance)}</b>",
        parse_mode='HTML',
    )


# ---------------------------------------------------------------------------
# Handler registration
# ---------------------------------------------------------------------------
application.add_handler(CommandHandler(["wpocket", "pocket", "balance"], wpocket, block=False))
application.add_handler(CommandHandler(["wsend", "sendcoins", "pay"], wsend, block=False))
application.add_handler(CommandHandler(["wtop", "cointop"], wtop, block=False))
application.add_handler(CommandHandler(["wadd", "addcoins"], wadd, block=False))
application.add_handler(CommandHandler(["wremove", "removecoins"], wremove, block=False))
