from html import escape
import math

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler

from NoxxNetwork import application, user_collection, collection
from NoxxNetwork.rarity import rarity_symbol


# 10 waifus per page
CHARS_PER_PAGE = 10


def _build_page_kb(user_id: int, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """Page navigation buttons"""
    row = []
    if page > 0:
        row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"wdup:{user_id}:{page - 1}"))
    row.append(InlineKeyboardButton(f"Page {page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        row.append(InlineKeyboardButton("Next ➡️", callback_data=f"wdup:{user_id}:{page + 1}"))

    return InlineKeyboardMarkup([row])


async def wduplicate(update: Update, context: CallbackContext, page: int = 0, edit_query=None) -> None:
    user = update.effective_user
    user_id = user.id

    # ─── User collection fetch karo ────────────────────────────
    user_doc = await user_collection.find_one({'id': user_id})
    if not user_doc or not user_doc.get('characters'):
        text = "🌸 <b>You don't have any characters yet!</b>"
        if edit_query:
            await edit_query.edit_message_text(text, parse_mode='HTML')
        else:
            await update.message.reply_text(text, parse_mode='HTML')
        return

    characters = user_doc['characters']

    # ─── Count duplicates ──────────────────────────────────────
    counts = {}
    char_data = {}

    for c in characters:
        cid = str(c.get('id', ''))
        if not cid:
            continue
        counts[cid] = counts.get(cid, 0) + 1
        if cid not in char_data:
            char_data[cid] = c  # Pehli baar jo data mila wo save karo

    # Sirf wo chars jinki 2 ya usse zyada copies hain
    duplicates = {cid: count for cid, count in counts.items() if count > 1}

    if not duplicates:
        text = (
            "🔍 <b>No Duplicate Characters Found</b>\n\n"
            "Aapke paas kisi bhi character ki multiple copies nahi hain."
        )
        if edit_query:
            await edit_query.edit_message_text(text, parse_mode='HTML')
        else:
            await update.message.reply_text(text, parse_mode='HTML')
        return

    # ─── Sort by count (highest first) ─────────────────────────
    sorted_dupes = sorted(duplicates.items(), key=lambda x: x[1], reverse=True)
    total_dupes = len(sorted_dupes)

    # ─── Pagination ────────────────────────────────────────────
    total_pages = max(1, math.ceil(total_dupes / CHARS_PER_PAGE))
    page = max(0, min(page, total_pages - 1))
    start = page * CHARS_PER_PAGE
    end = start + CHARS_PER_PAGE
    page_items = sorted_dupes[start:end]

    # ─── Build message ─────────────────────────────────────────
    text = f"🔁 <b>{escape(user.first_name or 'Your')}'s Duplicate Characters</b>\n"
    text += f"📊 Total Unique Duplicates: <b>{total_dupes}</b>\n"
    text += f"📄 Page {page + 1}/{total_pages}\n\n"

    for idx, (cid, count) in enumerate(page_items, start=start + 1):
        c = char_data[cid]
        name = escape(str(c.get('name', 'Unknown')))
        anime = escape(str(c.get('anime', 'Unknown')))
        rarity = escape(str(c.get('rarity', '⚪ Common')))
        symbol = rarity_symbol(c.get('rarity'))

        text += (
            f"{idx}. {symbol} <b>{name}</b>\n"
            f"   🆔 <code>{cid}</code> | 🎴 {anime}\n"
            f"   🗂 Copies: <b>×{count}</b>\n\n"
        )

    reply_markup = _build_page_kb(user_id, page, total_pages)

    # ─── Send or Edit ──────────────────────────────────────────
    try:
        if edit_query:
            await edit_query.edit_message_text(
                text=text,
                parse_mode='HTML',
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                text=text,
                parse_mode='HTML',
                reply_markup=reply_markup
            )
    except Exception:
        # Agar text same hai to ignore karo
        pass


# ─────────────────────────────────────────────────────────────
# Callback Handler (Pagination)
# ─────────────────────────────────────────────────────────────
async def wduplicate_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    if data == "noop":
        return

    if data.startswith("wdup:"):
        try:
            _, owner_id_s, page_s = data.split(":")
            owner_id = int(owner_id_s)
            page = int(page_s)
        except (ValueError, IndexError):
            return

        # 🔥 Only owner can navigate their duplicates
        if query.from_user.id != owner_id:
            await query.answer("This is not your list!", show_alert=True)
            return

        # Dummy update object pass karna hai jo `update.effective_user.id` de sake
        # Kyunki asli query me user id hoti hai, wo already match ho chuki hai
        class FakeUser:
            def __init__(self, u):
                self.id = u.id
                self.first_name = u.first_name
                self.username = u.username

        class FakeUpdate:
            def __init__(self, q):
                self.effective_user = FakeUser(q.from_user)

        fake_update = FakeUpdate(query)
        await wduplicate(fake_update, context, page=page, edit_query=query)


# ─────────────────────────────────────────────────────────────
# Handler Registration
# ─────────────────────────────────────────────────────────────
application.add_handler(CommandHandler(["wduplicate", "dupes", "wdupes"], wduplicate, block=False))
application.add_handler(CallbackQueryHandler(wduplicate_callback, pattern=r'^(wdup:|noop$)', block=False))
