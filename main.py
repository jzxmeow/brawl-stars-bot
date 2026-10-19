import asyncio
import logging
import os
import time
from urllib.parse import quote

import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from card_generator import generate_cards

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

BOT_TOKEN = os.environ["BOT_TOKEN"]
BRAWL_API_KEY = os.environ["BRAWL_API_KEY"]
API_URL = "https://api.brawlstars.com/v1"
HEADERS = {
    "Authorization": f"Bearer {BRAWL_API_KEY}",
    "Accept": "application/json",
}


def api_get(path):
    response = requests.get(f"{API_URL}{path}", headers=HEADERS, timeout=20)
    if response.status_code == 200:
        return response.json(), None
    logging.warning("Brawl API returned HTTP %s for path %s: %s",
                    response.status_code, path, response.text[:300])
    return None, response.status_code


def format_api_error(status):
    if status == 403:
        return "⛔ API отклонил запрос. Проверь ключ и разрешённый IP."
    if status == 404:
        return "Игрок не найден. Проверь тег."
    if status == 429:
        return "Слишком много запросов. Попробуй позже."
    return f"Ошибка Brawl Stars API: HTTP {status}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💎 Привет! Это Meta Helper!\n\n"
        "Я покажу статистику аккаунта и создам карточки бойцов.\n\n"
        "Используй команду:\n"
        "/player #ТВОЙТЕГ"
    )


async def player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Укажи тег игрока.\nПример: /player #8CG8LUJ")
        return

    tag = context.args[0].strip().lstrip("#").upper()
    if not tag or len(tag) > 20 or not tag.isalnum():
        await update.message.reply_text("Проверь тег и попробуй снова.")
        return

    await update.message.reply_text("🔎 Ищу игрока...")
    try:
        data, error = api_get(f"/players/%23{quote(tag, safe='')}")
        if error:
            await update.message.reply_text(format_api_error(error))
            return

        # Reuse the profile response when the user taps a card button shortly after
        # /player, avoiding a second official API request on the normal path.
        context.user_data.setdefault("player_cache", {})[tag] = {
            "timestamp": time.monotonic(),
            "data": data,
        }

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("⚡ Силы бойцов", callback_data=f"card:power:{tag}"),
            InlineKeyboardButton("🏆 Кубки бойцов", callback_data=f"card:trophies:{tag}"),
        ]])
        await update.message.reply_text(
            f"⭐ Игрок: {data.get('name', 'Неизвестно')}\n"
            f"🏆 Трофеи аккаунта: {data.get('trophies', 0)}\n"
            f"📈 Рекорд: {data.get('highestTrophies', 0)}\n\n"
            "Какую карточку генерируем?",
            reply_markup=keyboard,
        )
    except requests.RequestException:
        logging.exception("Brawl API connection failed")
        await update.message.reply_text("Не удалось подключиться к API. Попробуй позже.")


async def generate_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer("Готовлю карточку…")
    except BadRequest as exc:
        if "Query is too old" in str(exc) or "query id is invalid" in str(exc):
            logging.warning("Callback query expired; continuing card generation.")
        else:
            raise
    try:
        _, mode, tag = query.data.split(":", 2)
        status_message = await query.message.reply_text("🎨 Собираю портреты и статистику…")

        # Use the cached /player response if it is recent. Fall back to the API
        # when the user opens an old button or the cache is missing.
        cached = context.user_data.get("player_cache", {}).get(tag)
        if cached and time.monotonic() - cached.get("timestamp", 0) < 180:
            player_data = cached["data"]
        else:
            player_data, error = api_get(f"/players/%23{quote(tag, safe='')}")
            if error:
                await status_message.edit_text(format_api_error(error))
                return

        brawlers = player_data.get("brawlers", [])
        if not brawlers:
            await status_message.edit_text(
                "API не вернул список бойцов этого аккаунта. Проверь ответ API и логи FadeHost."
            )
            return

        player_data["tag"] = tag
        pages = await asyncio.to_thread(generate_cards, player_data, brawlers, mode)
        if not pages:
            await status_message.edit_text("Не нашёл бойцов для генерации карточки.")
            return

        await status_message.delete()
        for photo, caption in pages:
            await query.message.reply_photo(photo=photo, caption=caption)
            photo.close()
    except requests.RequestException:
        logging.exception("Brawl API connection failed")
        await query.message.reply_text("Не удалось подключиться к API. Попробуй позже.")
    except Exception:
        logging.exception("Card generation failed")
        await query.message.reply_text(
            "Не получилось создать карточку. Попробуй ещё раз. Если ошибка повторяется, проверь логи хостинга."
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.error("Unhandled Telegram update error", exc_info=context.error)


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("player", player))
    app.add_handler(CallbackQueryHandler(
        generate_card, pattern=r"^card:(power|trophies):[A-Z0-9]+$"
    ))
    app.add_error_handler(error_handler)
    app.run_polling()


if __name__ == "__main__":
    main()
