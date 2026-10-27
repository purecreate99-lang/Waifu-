"""
Football Game — /foot command with native Telegram dice animation.

Uses coin.py helpers (add_coins, coins_collection) so the balance stays
shared and no duplicate economy logic exists.
"""
import time
from html import escape

from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from NoxxNetwork import (
    application,
    db,
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


# ---------------------------------------------------------------------------
# Config (separate from bowling)
# ---------------------------------------------------------------------------
FOOT_COOLDOWN = 40              # seconds between kicks
FOOT_CHANCES_MAX = 6            # max chances
FOOT_WINDOW_DURATION = 12 * 3600  # 12h full-refill window
FOOT_REGEN_INTERVAL = 3600      # +1 chance per hour

# Native Telegram dice value → reward
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get_foot_state(doc: dict, now: int) -> dict:
    """Normalize football state (init, hourly regen, 12h refill)."""
    chances = doc.get('football_chances')
    window_start = int(doc.get('football_window_start', now))
    last_play = int(doc.get('football_last_play', 0))
    last_regen = int(doc.get('football_last_regen', now))

    # 🆕 First-time user
    if chances is None:
        return {
            'chances': FOOT_CHANCES_MAX,
            'window_start': now,
            'last_play': 0,
            'last_regen': now,
        }

    chances = int(chances)

    # 🔄 12-hour full refill window
    if now - window_start >= FOOT_WINDOW_DURATION:
        return {
            'chances': FOOT_CHANCES_MAX,
            'window_start': now,
            'last_play': last_play,
            'last_regen': now,
        }

    # 🕐 Hourly regen
    if chances < FOOT_CHANCES_MAX:
        hours_passed = (now - last_regen) // FOOT_REGEN_INTERVAL
        if hours_passed > 0:
            chances = min(FOOT_CHANCES_MAX, chances + hours_passed)
            last_regen += hours_passed * FOOT_REGEN_INTERVAL
    else:
        last_regen = now

    return {
        'chances': chances,
        'window_start': window_start,
        'last_play': last_play,
        'last_regen': last_regen,
    }


async def _save_foot_state(user_id: int, state: dict, extra: dict = None) -> None:
    fields = {
        'football_chances': state['chances'],
        'football_window_start': state['window_start'],
        'football_last_play': state['last_play'],
        'football_last_regen': state['last_regen'],
    }
    if extra:
        fields.update(extra)
    await coins_collection.update_one(
        {'user_id': user_id},
        {'$set': fields},
        upsert=True,
    )


# ---------------------------------------------------------------------------
# /foot — Football Game (MAIN CHAT ONLY)
# ---------------------------------------------------------------------------
async def foot(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id

    # 🚫 Only MAIN_CHAT_ID
    if chat_id != MAIN_CHAT_ID:
        await update.message.reply_text("⚠️ Please use /foot only in the Main chat!")
        return

    user = update.effective_user
    user_id = user.id
    now = int(time.time())

    # ─── Load state ─────────────────────────────────────────────
    doc = await coins_collection.find_one({'user_id': user_id}) or {}
    state = _get_foot_state(doc, now)

    # ⏳ Cooldown
    if state['last_play'] and (now - state['last_play']) < FOOT_COOLDOWN:
        remaining = FOOT_COOLDOWN - (now - state['last_play'])
        await update.message.reply_text(
            f"⏳ Please wait {remaining}s before your next /foot kick!"
        )
        await _save_foot_state(user_id, state)
        return

    # 🎟 Chances
    if state['chances'] <= 0:
        await update.message.reply_text(
            f"🎟 You have no football chances left!\n\n"
            f"🕐 +1 chance every hour\n"
            f"⚽ Full refill (6) every 12 hours."
        )
        await _save_foot_state(user_id, state)
        return

    # ─── Send native football dice ─────────────────────────────
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

    # ─── Consume chance + cooldown ─────────────────────────────
    state['chances'] -= 1
    state['last_play'] = now
    await _save_foot_state(user_id, state)

    # ─── Add coins ─────────────────────────────────────────────
    await add_coins(user_id, reward)

    # ─── Short result message (same style as bowling) ──────────
    chances_left = state['chances']

    result = (
        f"{label}\n"
        f"🎉 Yᴏᴜ ᴡᴏɴ <b>{CURRENCY_SYMBOL}{_fmt(reward)} {CURRENCY}</b>!\n"
        f"🎯 Rᴇᴍᴀɪɴɪɴɢ Cʜᴀɴᴄᴇs: <b>{chances_left}/{FOOT_CHANCES_MAX}</b>"
    )

    await update.message.reply_text(result, parse_mode='HTML')


# ---------------------------------------------------------------------------
# /footstatus
# ---------------------------------------------------------------------------
async def footstatus(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    now = int(time.time())

    doc = await coins_collection.find_one({'user_id': user.id}) or {}
    state = _get_foot_state(doc, now)
    await _save_foot_state(user.id, state)

    chances = state['chances']
    cooldown_left = 0
    if state['last_play']:
        elapsed = now - state['last_play']
        if elapsed < FOOT_COOLDOWN:
            cooldown_left = FOOT_COOLDOWN - elapsed

    refill_in = max(0, FOOT_WINDOW_DURATION - (now - state['window_start']))
    rh = refill_in // 3600
    rm = (refill_in % 3600) // 60

    if chances < FOOT_CHANCES_MAX:
        next_regen = max(0, FOOT_REGEN_INTERVAL - (now - state['last_regen']))
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
        + (f"{cooldown_left}s" if cooldown_left else "Ready ✅") + "\n"
        f"🕐 <b>Next +1:</b> {next_regen_text}\n"
        f"🔄 <b>Full refill in:</b> {rh}h {rm}m {rs}s",
        parse_mode='HTML',
    )


# ---------------------------------------------------------------------------
# Handler registration
# ---------------------------------------------------------------------------
application.add_handler(CommandHandler(["foot"], foot, block=False))
application.add_handler(CommandHandler(["footstatus", "fstatus"], footstatus, block=False))
