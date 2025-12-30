import os
import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
import logging
from gemini import (
    quota_status,
    remaining_total_quota,
    best_available_model,
    has_any_quota,
    ask as ask_gemini,
)

# async def notify_shutdown(app: Application, reason: str = "Server shutting down"):
# try:
#     # await app.bot.send_message(
#     #     chat_id=ADMIN_CHAT_ID,
#     #     text=f"⚠️ 機械人即將關閉\n原因：{reason}",
#     # )
# except Exception as e:
#     logger.error("Failed to send shutdown notice: %s", e)


load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3-vl:4b")
TELEGRAM_MAX_LEN = 4000

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("telegram-bot")


def ask_ollama(prompt: str) -> str:
    r = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
        },
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["response"].strip()


async def gemini_quota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = quota_status()
    total_remaining = remaining_total_quota()
    next_model = best_available_model()

    lines = ["🤖 Gemini 配額狀態"]

    for model, info in stats.items():
        lines.append(
            f"- {model.split('/')[-1]}: "
            f"{info['used']} / {info['limit']} "
            f"(剩餘 {info['remaining']})"
        )

    lines.append("")
    lines.append(f"📊 總剩餘次數：{total_remaining}")
    lines.append(
        "🧠 下一個可用模型：" f"{next_model.split('/')[-1] if next_model else '❌ 無'}"
    )

    await update.message.reply_text("\n".join(lines))


def is_bot_mentioned(update: Update, bot_username: str) -> bool:
    entities = update.message.entities or []
    for e in entities:
        if e.type == "mention":
            mention = update.message.text[e.offset : e.offset + e.length]
            if mention.lower() == f"@{bot_username.lower()}":
                return True
    return False


def has_command(update: Update) -> bool:
    entities = update.message.entities or []
    return any(e.type == "bot_command" for e in entities)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message

    if not msg or not msg.text:
        return

    chat_type = msg.chat.type
    bot_username = context.bot.username
    user = msg.from_user.username or msg.from_user.id
    text_raw = msg.text

    logger.info(
        "📩 Incoming | chat=%s | user=%s | text=%r",
        chat_type,
        user,
        text_raw,
    )

    # 1. Ignore all commands
    if any(e.type == "bot_command" for e in (msg.entities or [])):
        logger.info("⏭ Ignored: bot command detected")
        return

    # 2. In group chats, reply ONLY if mentioned
    if chat_type in ("group", "supergroup"):
        mentioned = False
        for e in msg.entities or []:
            if e.type == "mention":
                mention = msg.text[e.offset : e.offset + e.length]
                if mention.lower() == f"@{bot_username.lower()}":
                    mentioned = True
                    break

        if not mentioned:
            logger.info("⏭ Ignored: group message without mention")
            return

        logger.info("✅ Bot mentioned in group")

    # 3. Clean text (remove bot mention)
    text = msg.text.replace(f"@{bot_username}", "").strip()
    if not text:
        return

    logger.info("🧠 Sending to Ollama | prompt=%r", text)

    # 4. Check Gemini quota BEFORE calling
    if not has_any_quota():
        logger.warning("⛔ Gemini quota exhausted")
        await msg.reply_text("⚠️ 今日 AI 配額已用完，聽日再試 🙏")
        return

    next_model = best_available_model()
    logger.info(
        "🧠 Sending to Gemini | model=%s | prompt=%r",
        next_model,
        text,
    )

    await msg.reply_text("🤔 我諗諗先，你等我一陣...")

    try:
        reply = ask_gemini(text)
        logger.info("🤖 Ollama reply length=%d", len(reply))
    except Exception as e:
        logger.exception("❌ Gemini error")
        reply = f"⚠️ Gemini error:\n{e}"

    await msg.reply_text(reply)


async def on_startup(app: Application):
    logger.info("🚀 Bot started")
    # Optional: notify startup
    # await app.bot.send_message(ADMIN_CHAT_ID, "🤖 Bot started")


async def on_shutdown(app: Application):
    logger.warning("🛑 Bot shutting down")
    # await notify_shutdown(app, reason="Graceful shutdown")


async def send_long_message(msg, text: str):
    for i in range(0, len(text), TELEGRAM_MAX_LEN):
        await msg.reply_text(text[i : i + TELEGRAM_MAX_LEN])


async def quota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = quota_status()
    total_remaining = remaining_total_quota()
    next_model = best_available_model()

    lines = ["🤖 Gemini 配額狀態"]

    for model, info in stats.items():
        lines.append(
            f"- {model.split('/')[-1]}: "
            f"{info['used']} / {info['limit']} "
            f"(剩餘 {info['remaining']})"
        )

    lines.append("")
    lines.append(f"📊 總剩餘次數：{total_remaining}")
    lines.append(
        f"🧠 下一個可用模型：" f"{next_model.split('/')[-1] if next_model else '❌ 無'}"
    )

    await update.message.reply_text("\n".join(lines))


async def ask_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return

    text = " ".join(context.args).strip()
    if not text:
        await msg.reply_text("⚠️ 請喺指令後面輸入問題，例如：\n/gemini 乜嘢係 token")
        return

    if not has_any_quota():
        await msg.reply_text("⛔ 今日 Gemini 配額已用完，改用本地 AI 👇")
        reply = ask_ollama(text)
        await msg.reply_text(reply)
        return

    await msg.reply_text("🤔 諗緊，你等我一陣...")

    try:
        reply = ask_gemini(text)
    except Exception as e:
        logger.exception("❌ Gemini error, fallback to Ollama")
        reply = ask_ollama(text)

    await send_long_message(msg, reply)


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN missing in .env")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(on_startup)
        .post_shutdown(on_shutdown)
        .build()
    )

    app.add_handler(CommandHandler("ask", ask_cmd))
    app.add_handler(CommandHandler("gemini_quota", gemini_quota))
    # app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("🤖 Telegram bot running (polling)...")
    app.run_polling()


if __name__ == "__main__":
    main()
