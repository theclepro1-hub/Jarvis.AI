import logging
import threading
import time

from .branding import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)

try:
    import telebot
except Exception:
    telebot = None


def _normalize_text(text: str) -> str:
    return " ".join(str(text or "").lower().replace("ё", "е").split())

# =========================================================
# TELEGRAM BOT (optional)
# =========================================================

class TelegramBot:
    def __init__(self, token, allowed_user_id, process_callback, display_name=""):
        self.token = (token or "").strip()
        self.allowed_user_id = self._normalize_user_id(allowed_user_id)
        self.display_name = display_name or ""
        self.process_callback = process_callback
        self.bot = None
        self.thread = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._conflict_count = 0

    @staticmethod
    def _normalize_user_id(value):
        try:
            return int(value) if value not in (None, "", 0, "0") else 0
        except Exception:
            return 0

    def start(self):
        if not self.token or self.token == "YOUR_TOKEN_HERE":
            logger.info("Telegram bot is disabled: token is empty.")
            return
        if not self.allowed_user_id:
            logger.info("Telegram bot is disabled: allowed user id is empty.")
            return
        with self._lock:
            if self.thread and self.thread.is_alive():
                return
            self._stop_event.clear()
            self._conflict_count = 0
            self.thread = threading.Thread(target=self._run, daemon=True, name="TelegramBotThread")
            self.thread.start()

    def _run(self):
        self.bot = telebot.TeleBot(self.token)

        @self.bot.message_handler(commands=['start'])
        def start_cmd(msg):
            if self.allowed_user_id and msg.from_user.id != self.allowed_user_id:
                return
            name = self.display_name.strip() or (msg.from_user.first_name or "друг")
            self.bot.reply_to(msg, f"Привет, {name}! Я Джарвис.")

        @self.bot.message_handler(content_types=['sticker'])
        def handle_sticker(msg):
            if self.allowed_user_id and msg.from_user.id != self.allowed_user_id:
                return
            payload = ""
            try:
                payload = str(getattr(getattr(msg, "sticker", None), "emoji", "") or "").strip()
            except Exception:
                payload = ""
            if not payload:
                payload = "🙂"
            self.bot.send_chat_action(msg.chat.id, 'typing')
            resp = self.process_callback(payload)
            if len(resp) > 4000:
                resp = resp[:4000] + "..."
            self.bot.reply_to(msg, resp or payload)

        @self.bot.message_handler(content_types=['text'])
        def handle_text(msg):
            if self.allowed_user_id and msg.from_user.id != self.allowed_user_id:
                return
            if not msg.text:
                return
            self.bot.send_chat_action(msg.chat.id, 'typing')
            resp = self.process_callback(msg.text)
            if len(resp) > 4000:
                resp = resp[:4000] + "..."
            self.bot.reply_to(msg, resp or "✅ Выполнено")

        while not self._stop_event.is_set():
            try:
                try:
                    self.bot.remove_webhook()
                except Exception:
                    pass
                poll_kwargs = dict(skip_pending=True, timeout=20, long_polling_timeout=20)
                try:
                    self.bot.infinity_polling(logger_level=logging.CRITICAL, **poll_kwargs)
                except TypeError:
                    self.bot.infinity_polling(**poll_kwargs)
                break
            except Exception as e:
                err = str(e or "")
                norm = _normalize_text(err)
                is_conflict = "409" in norm and ("getupdates" in norm or "terminated by other" in norm or "conflict" in norm)
                if is_conflict:
                    self._conflict_count += 1
                    # При первом конфликте ждем 10 секунд, при повторных - останавливаем polling
                    if self._conflict_count >= 2:
                        logger.warning(
                            "Telegram polling conflict (409): другой клиент использует этот bot token. "
                            "Проверьте, что запущен только один polling-процесс."
                        )
                        logger.warning("Telegram polling отключен в этой сессии, чтобы не спамить ошибками 409.")
                        break
                    logger.debug(f"Telegram polling conflict (409) #{self._conflict_count}, retry after 10s...")
                    time.sleep(10)
                    continue
                logger.error(f"Telegram error: {e}")
                time.sleep(5)
                if self._stop_event.is_set():
                    break

    def send_message(self, user_id, text):
        target_id = self._normalize_user_id(user_id)
        if self.bot and self.allowed_user_id and target_id == self.allowed_user_id:
            try:
                self.bot.send_message(target_id, text)
            except Exception as e:
                logger.error(f"Telegram send error: {e}")

    def stop(self):
        self._stop_event.set()
        if self.bot:
            try:
                self.bot.stop_polling()
            except Exception:
                pass
        try:
            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=2.5)
        except Exception:
            pass


__all__ = ["TelegramBot"]
