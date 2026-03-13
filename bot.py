"""
Telegram-бот для запуска парсера чатов.
Кнопка: Парсить
"""
import asyncio
import logging
import os

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

from main import run_parser, _parse_chat_id

WAITING_CHAT = 1

# Логи в Telegram
LOG_LINES: list = []

# Логгеры, связанные с парсингом (без telethon и др.)
PARSER_LOGGERS = ("__main__", "collectors", "profile_parser", "clients", "channel_filter")


class ParserLogFilter(logging.Filter):
    """Пропускает только логи парсера."""

    def filter(self, record):
        return record.name in PARSER_LOGGERS


class TelegramLogHandler(logging.Handler):
    """Собирает логи парсера для отправки в Telegram."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.addFilter(ParserLogFilter())

    def emit(self, record):
        try:
            if self.filter(record):
                msg = self.format(record)
                if msg:
                    LOG_LINES.append(msg)
        except Exception:
            pass


async def send_logs_loop(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, stop_event: asyncio.Event
):
    """Периодически отправляет накопленные логи, пока не сигнал остановки."""
    last_sent = 0
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=15.0)
        except asyncio.TimeoutError:
            pass
        if stop_event.is_set():
            break
        if len(LOG_LINES) > last_sent:
            batch = LOG_LINES[last_sent : last_sent + 25]
            last_sent += len(batch)
            text = "\n".join(batch)
            if len(text) > 3900:
                text = "…\n" + text[-3900:]
            if text.strip():
                try:
                    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"<pre>{safe}</pre>",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass


def get_main_keyboard(with_cancel=False):
    row1 = [KeyboardButton("Парсить")]
    rows = [row1]
    if with_cancel:
        rows.append([KeyboardButton("Отмена")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


async def parse_cmd_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /parse — если есть аргументы, сразу парсим; иначе запрашиваем."""
    if context.args:
        chat_ids = [_parse_chat_id(x) for x in context.args]
        return await do_parse(update, context, chat_ids)
    return await button_parse(update, context)


async def button_parse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кнопка Парсить — запрашиваем chat."""
    await update.message.reply_text(
        "Введи username чата для парсинга:\n"
        "Пример: trafficshaman\n"
        "Или несколько через пробел: chat1 chat2",
        reply_markup=get_main_keyboard(with_cancel=True),
    )
    return WAITING_CHAT


async def run_parse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода chat от пользователя."""
    text = (update.message.text or "").strip()
    if not text or text == "Парсить":
        await update.message.reply_text("Введи username чата (например trafficshaman)")
        return WAITING_CHAT

    chat_ids = [_parse_chat_id(x) for x in text.split()]
    return await do_parse(update, context, chat_ids)


async def do_parse(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_ids: list):
    """Выполняет парсинг и отправляет результат."""
    chat_id = update.effective_chat.id

    await update.message.reply_text(
        f"Старт парсинга: {', '.join(str(c) for c in chat_ids)}\n"
        "Логи буду присылать каждые ~15 сек."
    )

    handler = TelegramLogHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S"))
    root = logging.getLogger()
    root.addHandler(handler)
    LOG_LINES.clear()
    stop_event = asyncio.Event()

    log_task = asyncio.create_task(send_logs_loop(context, chat_id, stop_event))
    try:
        result_path = await run_parser(chat_ids)
    except Exception as e:
        logging.exception("Ошибка парсинга")
        await update.message.reply_text(f"Ошибка: {e}")
        return ConversationHandler.END
    finally:
        stop_event.set()
        log_task.cancel()
        try:
            await log_task
        except asyncio.CancelledError:
            pass
        root.removeHandler(handler)

    # Отправляем оставшиеся логи
    if LOG_LINES:
        text = "\n".join(LOG_LINES[-40:])
        if len(text) > 4000:
            text = text[-4000:]
        safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"<pre>{safe}</pre>",
                parse_mode="HTML",
            )
        except Exception:
            pass

    # Отправляем результат
    if result_path and os.path.exists(result_path):
        with open(result_path, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=os.path.basename(result_path),
                caption="Результат парсинга",
            )
    else:
        await update.message.reply_text("Парсинг завершён, но файл не создан (возможно, нет данных).")

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выход из диалога."""
    await update.message.reply_text("Отменено.", reply_markup=get_main_keyboard())
    return ConversationHandler.END


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик /start."""
    await update.message.reply_text(
        "Парсер чатов.\nНажми кнопку для действия:",
        reply_markup=get_main_keyboard(),
    )


def main():
    try:
        import config as _cfg
    except ImportError:
        import config.example as _cfg
    token = getattr(_cfg, "BOT_TOKEN", None)
    if not token:
        print("Добавь BOT_TOKEN в config.py (создай бота через @BotFather)")
        return

    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^Парсить$"), button_parse),
            CommandHandler("parse", parse_cmd_entry),
        ],
        states={
            WAITING_CHAT: [
                MessageHandler(filters.Regex("^Отмена$"), cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, run_parse),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel), MessageHandler(filters.Regex("^Отмена$"), cancel)],
    )

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(conv)

    print("Бот запущен. Нажми Парсить или введи /parse <chat>")
    app.run_polling()


if __name__ == "__main__":
    main()
