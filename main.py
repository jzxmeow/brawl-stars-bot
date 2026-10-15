
import os
import logging
import requests

from urllib.parse import quote
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

BOT_TOKEN = os.environ["BOT_TOKEN"]
BRAWL_API_KEY = os.environ["BRAWL_API_KEY"]

API_URL = "https://api.brawlstars.com/v1"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⭐ Brawl Stats Bot\n\n"
        "Я помогу изучить твой аккаунт Brawl Stars!\n\n"
        "Отправь тег так:\n"
        "/player #ТВОЙТЕГ\n\n"
        "Узнать внешний IP сервера:\n"
        "/ip"
    )


async def ip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        response = requests.get(
            "https://api.ipify.org",
            timeout=10,
        )
        response.raise_for_status()

        ip = response.text.strip()

        await update.message.reply_text(
            f"🌐 Внешний IP сервера FadeHost:\n{ip}"
        )

    except requests.RequestException as e:
        logging.exception("IP lookup failed")
        await update.message.reply_text(
            "❌ Не удалось узнать IP сервера.\n"
            f"Ошибка: {type(e).__name__}\n"
            "Возможно, хост блокирует внешние запросы."
        )


async def player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Укажи тег игрока.\nПример: /player #8CG8LUJ"
        )
        return

    tag = context.args[0].strip().lstrip("#").upper()

    if not tag or len(tag) > 20:
        await update.message.reply_text("Проверь тег и попробуй снова.")
        return

    url = f"{API_URL}/players/%23{quote(tag, safe='')}"

    headers = {
        "Authorization": f"Bearer {BRAWL_API_KEY}",
        "Accept": "application/json",
    }

    await update.message.reply_text("🔎 Ищу игрока...")

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=20,
        )

        if response.status_code == 200:
            data = response.json()

            brawlers = data.get("brawlers", [])
            brawlers.sort(
                key=lambda b: b.get("power", 0),
                reverse=True,
            )

            result = [
                f"⭐ Игрок: {data.get('name', 'Неизвестно')}",
                f"🏆 Трофеи: {data.get('trophies', 0)}",
                f"📈 Рекорд: {data.get('highestTrophies', 0)}",
                "",
                f"🥊 Бравлеров в ответе API: {len(brawlers)}",
            ]

            for b in brawlers[:15]:
                result.append(
                    f"• {b.get('name', '?')} — "
                    f"сила {b.get('power', '?')}, "
                    f"трофеи {b.get('trophies', 0)}"
                )

            await update.message.reply_text(
                "\n".join(result)[:4000]
            )

        elif response.status_code == 403:
            await update.message.reply_text(
                "⛔ API отклонил запрос. "
                "Проверь ключ и разрешённый IP."
            )

        elif response.status_code == 404:
            await update.message.reply_text(
                "Игрок не найден. Проверь тег."
            )

        elif response.status_code == 429:
            await update.message.reply_text(
                "Слишком много запросов. Попробуй позже."
            )

        else:
            logging.warning(
                "Brawl API status: %s",
                response.status_code,
            )
            await update.message.reply_text(
                f"Ошибка API: HTTP {response.status_code}"
            )

    except requests.RequestException:
        logging.exception("Brawl API connection failed")
        await update.message.reply_text(
            "Не удалось подключиться к API. Попробуй позже."
        )


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("player", player))
    app.add_handler(CommandHandler("ip", ip_command))

    app.run_polling()


if __name__ == "__main__":
    main()
