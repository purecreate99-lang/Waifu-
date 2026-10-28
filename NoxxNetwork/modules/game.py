
"""
Football + Basketball Games

/foot       - Play Football
/footstatus - Check Football Status
/fstatus    - Football Status Alias

/ball       - Play Basketball
/ballstatus - Check Basketball Status
/bstatus    - Basketball Status Alias

Both games use native Telegram dice animations and share the
existing coin.py economy. Each game has independent chances,
cooldowns, regeneration, and refill timers.
"""

import time
from html import escape

from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from NoxxNetwork import (
    application,
    MAIN_CHAT_ID,
    LOGGER,
)

from NoxxNetwork.modules.coin import (
    coins_collection,
    add_coins,
    get_balance,
    CURRENCY,
    CURRENCY_SYMBOL,
    _fmt,
)


# =====================================================================
# FOOTBALL CONFIG
# =====================================================================

FOOT_COOLDOWN = 40
FOOT_CHANCES_MAX = 6
FOOT_WINDOW_DURATION = 12 * 3600
FOOT_REGEN_INTERVAL = 3600

FOOT_REWARDS = {
    1: 10,
    2: 20,
    3: 40,
    4: 70,
    5: 100,
}

FOOT_LABELS = {
    1: "😔 Mɪssᴇᴅ Sʜᴏᴛ!",
    2: "🥅 Wᴇᴀᴋ Sʜᴏᴛ!",
    3: "⚽ Nɪᴄᴇ Kɪᴄᴋ!",
    4: "🔥 Aᴍᴀᴢɪɴɢ Sʜᴏᴛ!",
    5: "🏆 GOAL! Pᴇʀғᴇᴄᴛ Sʜᴏᴛ!",
}


# =====================================================================
# BASKETBALL CONFIG
# =====================================================================

BALL_COOLDOWN = 40
BALL_CHANCES_MAX = 6
BALL_WINDOW_DURATION = 12 * 3600
BALL_REGEN_INTERVAL = 3600

BALL_REWARDS = {
    1: 10,
    2: 20,
    3: 40,
    4: 70,
    5: 100,
}

BALL_LABELS = {
    1: "😔 Mɪssᴇᴅ Sʜᴏᴛ!",
    2: "🏀 Wᴇᴀᴋ Sʜᴏᴛ!",
    3: "🏀 Nɪᴄᴇ Sʜᴏᴛ!",
    4: "🔥 Aᴍᴀᴢɪɴɢ Sʜᴏᴛ!",
    5: "🏆 Pᴇʀғᴇᴄᴛ Sʜᴏᴛ!",
}


# =====================================================================
# FOOTBALL HELPERS
# =====================================================================

def _get_foot_state(doc: dict, now: int) -> dict:
    """Initialize football state, regenerate chances and refill every 12h."""

    chances = doc.get("football_chances")
    window_start = int(doc.get("football_window_start", now))
    last_play = int(doc.get("football_last_play", 0))
    last_regen = int(doc.get("football_last_regen", now))

    if chances is None:
        return {
            "chances": FOOT_CHANCES_MAX,
            "window_start": now,
            "last_play": 0,
            "last_regen": now,
        }

    chances = int(chances)

    if now - window_start >= FOOT_WINDOW_DURATION:
        return {
            "chances": FOOT_CHANCES_MAX,
            "window_start": now,
            "last_play": last_play,
            "last_regen": now,
        }

    if chances < FOOT_CHANCES_MAX:
        hours_passed = (now - last_regen) // FOOT_REGEN_INTERVAL

        if hours_passed > 0:
            chances = min(FOOT_CHANCES_MAX, chances + hours_passed)
            last_regen += hours_passed * FOOT_REGEN_INTERVAL
    else:
        last_regen = now

    return {
        "chances": chances,
        "window_start": window_start,
        "last_play": last_play,
        "last_regen": last_regen,
    }


async def _save_foot_state(
    user_id: int,
    state: dict,
    extra: dict = None,
) -> None:
    fields = {
        "football_chances": state["chances"],
        "football_window_start": state["window_start"],
        "football_last_play": state["last_play"],
        "football_last_regen": state["last_regen"],
    }

    if extra:
        fields.update(extra)

    await coins_collection.update_one(
        {"user_id": user_id},
        {"$set": fields},
        upsert=True,
    )


# =====================================================================
# BASKETBALL HELPERS
# =====================================================================

def _get_ball_state(doc: dict, now: int) -> dict:
    """Independent basketball state with hourly regeneration and 12h refill."""

    chances = doc.get("basketball_chances")
    window_start = int(doc.get("basketball_window_start", now))
    last_play = int(doc.get("basketball_last_play", 0))
    last_regen = int(doc.get("basketball_last_regen", now))

    if chances is None:
        return {
            "chances": BALL_CHANCES_MAX,
            "window_start": now,
            "last_play": 0,
            "last_regen": now,
        }

    chances = int(chances)

    if now - window_start >= BALL_WINDOW_DURATION:
        return {
            "chances": BALL_CHANCES_MAX,
            "window_start": now,
            "last_play": last_play,
            "last_regen": now,
        }

    if chances < BALL_CHANCES_MAX:
        hours_passed = (now - last_regen) // BALL_REGEN_INTERVAL

        if hours_passed > 0:
            chances = min(BALL_CHANCES_MAX, chances + hours_passed)
            last_regen += hours_passed * BALL_REGEN_INTERVAL
    else:
        last_regen = now

    return {
        "chances": chances,
        "window_start": window_start,
        "last_play": last_play,
        "last_regen": last_regen,
    }


async def _save_ball_state(
    user_id: int,
    state: dict,
    extra: dict = None,
) -> None:
    fields = {
        "basketball_chances": state["chances"],
        "basketball_window_start": state["window_start"],
        "basketball_last_play": state["last_play"],
        "basketball_last_regen": state["last_regen"],
    }

    if extra:
        fields.update(extra)

    await coins_collection.update_one(
        {"user_id": user_id},
        {"$set": fields},
        upsert=True,
    )


# =====================================================================
# /foot — FOOTBALL GAME
# =====================================================================

async def foot(update: Update, context: CallbackContext) -> None:
    if not update.effective_chat or not update.message:
        return

    if update.effective_chat.id != MAIN_CHAT_ID:
        await update.message.reply_text(
            "⚠️ Please use /foot only in the Main chat!"
        )
        return

    user = update.effective_user
    if not user:
        return

    user_id = user.id
    now = int(time.time())

    doc = await coins_collection.find_one({"user_id": user_id}) or {}
    state = _get_foot_state(doc, now)

    # Cooldown
    if state["last_play"] and now - state["last_play"] < FOOT_COOLDOWN:
        remaining = FOOT_COOLDOWN - (now - state["last_play"])

        await _save_foot_state(user_id, state)

        await update.message.reply_text(
            f"⏳ Please wait {remaining}s before your next football kick!"
        )
        return

    # Chances
    if state["chances"] <= 0:
        await _save_foot_state(user_id, state)

        await update.message.reply_text(
            "🎟 You have no football chances left!\n\n"
            "🕐 +1 chance every hour\n"
            "⚽ Full refill (6) every 12 hours."
        )
        return

    # Native Telegram football animation
    try:
        dice_msg = await update.message.reply_dice(emoji="⚽")
    except Exception as e:
        LOGGER.error(f"[foot] dice send failed: {e}")
        return

    if not dice_msg or not dice_msg.dice:
        return

    score = int(dice_msg.dice.value)
    reward = FOOT_REWARDS.get(score, 10)
    label = FOOT_LABELS.get(score, "⚽ Nɪᴄᴇ Kɪᴄᴋ!")

    # Consume chance and start cooldown
    state["chances"] -= 1
    state["last_play"] = int(time.time())

    await _save_foot_state(user_id, state)

    # Shared economy
    await add_coins(user_id, reward)

    result = (
        f"{label}\n\n"
        f"🎉 Yᴏᴜ ᴡᴏɴ <b>{CURRENCY_SYMBOL}{_fmt(reward)} "
        f"{CURRENCY}</b>!\n"
        f"🎯 Rᴇᴍᴀɪɴɪɴɢ Cʜᴀɴᴄᴇs: "
        f"<b>{state['chances']}/{FOOT_CHANCES_MAX}</b>"
    )

    await update.message.reply_text(result, parse_mode="HTML")


# =====================================================================
# /footstatus — FOOTBALL STATUS
# =====================================================================

async def footstatus(update: Update, context: CallbackContext) -> None:
    if not update.effective_user or not update.message:
        return

    user = update.effective_user
    now = int(time.time())

    doc = await coins_collection.find_one({"user_id": user.id}) or {}
    state = _get_foot_state(doc, now)

    await _save_foot_state(user.id, state)

    chances = state["chances"]
    cooldown_left = 0

    if state["last_play"]:
        elapsed = now - state["last_play"]

        if elapsed < FOOT_COOLDOWN:
            cooldown_left = FOOT_COOLDOWN - elapsed

    refill_in = max(
        0,
        FOOT_WINDOW_DURATION - (now - state["window_start"]),
    )
    rh = refill_in // 3600
    rm = (refill_in % 3600) // 60
    rs = refill_in % 60

    if chances < FOOT_CHANCES_MAX:
        next_regen = max(
            0,
            FOOT_REGEN_INTERVAL - (now - state["last_regen"]),
        )
        nh = next_regen // 3600
        nm = (next_regen % 3600) // 60
        next_regen_text = f"{nh}h {nm}m"
    else:
        next_regen_text = "Full ✅"

    name = escape(user.first_name or "User")

    await update.message.reply_text(
        f"⚽ <b>{name}'s Football Status</b>\n\n"
        f"🎟 <b>Chances:</b> {chances}/{FOOT_CHANCES_MAX}\n"
        f"⏳ <b>Cooldown:</b> "
        f"{f'{cooldown_left}s' if cooldown_left else 'Ready ✅'}\n"
        f"🕐 <b>Next +1:</b> {next_regen_text}\n"
        f"🔄 <b>Full refill in:</b> {rh}h {rm}m {rs}s",
        parse_mode="HTML",
    )


# =====================================================================
# /ball — BASKETBALL GAME
# =====================================================================

async def ball(update: Update, context: CallbackContext) -> None:
    if not update.effective_chat or not update.message:
        return

    if update.effective_chat.id != MAIN_CHAT_ID:
        await update.message.reply_text(
            "⚠️ Please use /ball only in the Main chat!"
        )
        return

    user = update.effective_user
    if not user:
        return

    user_id = user.id
    now = int(time.time())

    doc = await coins_collection.find_one({"user_id": user_id}) or {}
    state = _get_ball_state(doc, now)

    # Basketball cooldown
    if state["last_play"] and now - state["last_play"] < BALL_COOLDOWN:
        remaining = BALL_COOLDOWN - (now - state["last_play"])

        await _save_ball_state(user_id, state)

        await update.message.reply_text(
            f"⏳ Wᴀɪᴛ <b>{remaining}s</b> ʙᴇғᴏʀᴇ ʏᴏᴜʀ "
            f"ɴᴇxᴛ ʙᴀsᴋᴇᴛʙᴀʟʟ sʜᴏᴛ! 🏀",
            parse_mode="HTML",
        )
        return

    # Basketball chances
    if state["chances"] <= 0:
        await _save_ball_state(user_id, state)

        await update.message.reply_text(
            "🏀 <b>Yᴏᴜ'ʀᴇ ᴏᴜᴛ ᴏғ sʜᴏᴛs!</b>\n\n"
            "🎟 Cʜᴀɴᴄᴇs: <b>0/6</b>\n"
            "🕐 +1 ᴄʜᴀɴᴄᴇ ᴇᴠᴇʀʏ ʜᴏᴜʀ\n"
            "🔄 Fᴜʟʟ ʀᴇғɪʟʟ ᴇᴠᴇʀʏ 12 ʜᴏᴜʀs!",
            parse_mode="HTML",
        )
        return

    # Native Telegram basketball animation
    try:
        dice_msg = await update.message.reply_dice(emoji="🏀")
    except Exception as e:
        LOGGER.error(f"[ball] dice send failed: {e}")
        await update.message.reply_text(
            "⚠️ Basketball animation failed. Your chance wasn't used."
        )
        return

    if not dice_msg or not dice_msg.dice:
        return

    score = int(dice_msg.dice.value)
    reward = BALL_REWARDS.get(score, 10)
    label = BALL_LABELS.get(score, "🏀 Nɪᴄᴇ Sʜᴏᴛ!")

    # Consume basketball chance and start its cooldown
    state["chances"] -= 1
    state["last_play"] = int(time.time())

    await _save_ball_state(user_id, state)

    # Shared economy
    await add_coins(user_id, reward)

    result = (
        f"{label}\n\n"
        f"🎉 Yᴏᴜ ᴡᴏɴ <b>{CURRENCY_SYMBOL}{_fmt(reward)} "
        f"{CURRENCY}</b>!\n"
        f"🎯 Rᴇᴍᴀɪɴɪɴɢ Sʜᴏᴛs: "
        f"<b>{state['chances']}/{BALL_CHANCES_MAX}</b>"
    )

    await update.message.reply_text(result, parse_mode="HTML")


# =====================================================================
# /ballstatus — BASKETBALL STATUS
# =====================================================================

async def ballstatus(update: Update, context: CallbackContext) -> None:
    if not update.effective_user or not update.message:
        return

    user = update.effective_user
    now = int(time.time())

    doc = await coins_collection.find_one({"user_id": user.id}) or {}
    state = _get_ball_state(doc, now)

    await _save_ball_state(user.id, state)

    chances = state["chances"]
    cooldown_left = 0

    if state["last_play"]:
        elapsed = now - state["last_play"]

        if elapsed < BALL_COOLDOWN:
            cooldown_left = BALL_COOLDOWN - elapsed

    refill_in = max(
        0,
        BALL_WINDOW_DURATION - (now - state["window_start"]),
    )
    rh = refill_in // 3600
    rm = (refill_in % 3600) // 60
    rs = refill_in % 60

    if chances < BALL_CHANCES_MAX:
        next_regen = max(
            0,
            BALL_REGEN_INTERVAL - (now - state["last_regen"]),
        )
        nh = next_regen // 3600
        nm = (next_regen % 3600) // 60
        next_regen_text = f"{nh}h {nm}m"
    else:
        next_regen_text = "Full ✅"

    name = escape(user.first_name or "User")

    await update.message.reply_text(
        f"🏀 <b>{name}'s Basketball Status</b>\n\n"
        f"🎟 <b>Shots:</b> {chances}/{BALL_CHANCES_MAX}\n"
        f"⏳ <b>Cooldown:</b> "
        f"{f'{cooldown_left}s' if cooldown_left else 'Ready ✅'}\n"
        f"🕐 <b>Next +1:</b> {next_regen_text}\n"
        f"🔄 <b>Full refill in:</b> {rh}h {rm}m {rs}s",
        parse_mode="HTML",
    )


# =====================================================================
# HANDLER REGISTRATION
# =====================================================================

application.add_handler(
    CommandHandler(["foot"], foot, block=False)
)

application.add_handler(
    CommandHandler(["footstatus", "fstatus"], footstatus, block=False)
)

application.add_handler(
    CommandHandler(["ball"], ball, block=False)
)

application.add_handler(
    CommandHandler(["ballstatus", "bstatus"], ballstatus, block=False)
)
