"""Telegram channel implementation."""

import asyncio
import time
from typing import TYPE_CHECKING

from loguru import logger
from telegram import BotCommand, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.request import HTTPXRequest

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.utils.helpers import ensure_dir

if TYPE_CHECKING:
    from nanobot.config.schema import TelegramConfig
    from nanobot.session.manager import SessionManager


class TelegramChannel(BaseChannel):
    """
    Telegram channel using python-telegram-bot.

    Supports:
    - Receiving messages
    - Sending messages (text, markdown)
    - Sending media (images, voice, audio)
    - Responding to /start, /reset commands
    - Typing indicators
    """

    def __init__(
        self,
        config: "TelegramConfig",
        bus: MessageBus,
        session_manager: "SessionManager | None" = None,
    ):
        super().__init__("telegram", bus, session_manager)
        self.config = config
        self._app: Application | None = None
        self._running = False
        self._typing_tasks: dict[int, asyncio.Task] = {}

    async def start(self) -> None:
        """Start the Telegram bot."""
        if not self.config.token:
            logger.error("Telegram bot token not configured")
            return

        self._running = True

        # Build the application with larger connection pool to avoid pool-timeout on long runs
        req = HTTPXRequest(
            connection_pool_size=16, pool_timeout=5.0, connect_timeout=30.0, read_timeout=30.0
        )
        builder = (
            Application.builder().token(self.config.token).request(req).get_updates_request(req)
        )
        if self.config.proxy:
            builder = builder.proxy(self.config.proxy).get_updates_proxy(self.config.proxy)
        self._app = builder.build()
        self._app.add_error_handler(self._on_error)

        # Add command handlers
        self._app.add_handler(CommandHandler("start", self._on_start))
        self._app.add_handler(CommandHandler("reset", self._on_reset))

        # Add message handler
        self._app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, self._on_message))

        # Start the application
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()

        # Set bot commands
        await self._app.bot.set_my_commands(
            [
                BotCommand("start", "Start or restart the bot"),
                BotCommand("reset", "Clear conversation history"),
            ]
        )

        logger.info("Telegram bot started")

        # Keep running until stopped
        while self._running:
            await asyncio.sleep(1)

    async def stop(self) -> None:
        """Stop the Telegram bot."""
        self._running = False
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()

    def _is_allowed(self, update: Update) -> bool:
        """Check if the user is allowed to use the bot."""
        if not self.config.allow_from:
            return True

        user = update.effective_user
        if not user:
            return False

        user_id = str(user.id)
        username = user.username or ""

        return user_id in self.config.allow_from or username in self.config.allow_from

    async def _on_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        if not self._is_allowed(update):
            return

        await update.message.reply_text(
            "Hello! I am nanobot. How can I help you today?\n\n"
            "Commands:\n"
            "/start - Start or restart the bot\n"
            "/reset - Clear conversation history"
        )

    async def _on_reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /reset command."""
        if not self._is_allowed(update):
            return

        chat_id = update.effective_chat.id
        session_key = f"telegram:{chat_id}"

        if self.session_manager:
            self.session_manager.delete(session_key)

        await update.message.reply_text("Conversation history cleared.")

    async def _on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming messages."""
        if not self._is_allowed(update):
            return

        chat_id = update.effective_chat.id
        user = update.effective_user
        message = update.message

        if not message:
            return

        # Extract text or caption
        content = message.text or message.caption or ""

        # Handle media
        media = []
        if message.photo:
            # Get the largest photo
            photo = message.photo[-1]
            file = await context.bot.get_file(photo.file_id)
            media.append(
                {
                    "type": "image",
                    "mime_type": "image/jpeg",
                    "url": file.file_path,
                    "file_id": photo.file_id,
                }
            )
        elif message.voice:
            voice = message.voice
            file = await context.bot.get_file(voice.file_id)
            media.append(
                {
                    "type": "voice",
                    "mime_type": voice.mime_type,
                    "url": file.file_path,
                    "file_id": voice.file_id,
                }
            )

        # Route to bus
        await self.publish_inbound(
            content=content,
            chat_id=str(chat_id),
            sender_id=str(user.id),
            media=media if media else None,
            metadata={
                "first_name": user.first_name,
                "last_name": user.last_name,
                "username": user.username,
            },
        )

        # Start typing indicator
        self._start_typing(chat_id)

    async def handle_outbound(self, msg: OutboundMessage) -> None:
        """Handle outbound messages from the bus."""
        if not self._app or not self._running:
            return

        chat_id = int(msg.chat_id)

        # Stop typing indicator
        self._stop_typing(chat_id)

        try:
            # Handle media in outbound if present
            if msg.media:
                for item in msg.media:
                    media_type = item.get("type", "file")
                    file_path = item.get("path")
                    content_data = item.get("content")

                    if not file_path and not content_data:
                        continue

                    # If we have binary content but no path, create a temp file
                    temp_path = None
                    if content_data and not file_path:
                        from nanobot.utils.helpers import get_data_path

                        temp_dir = ensure_dir(get_data_path() / "temp")
                        ext = self._get_extension(media_type, item.get("mime_type"))
                        temp_path = temp_dir / f"telegram_out_{int(time.time())}{ext}"
                        temp_path.write_bytes(content_data)
                        file_path = str(temp_path)

                    try:
                        if media_type == "image":
                            await self._app.bot.send_photo(
                                chat_id=chat_id, photo=open(file_path, "rb"), caption=msg.content
                            )
                        elif media_type == "voice":
                            await self._app.bot.send_voice(
                                chat_id=chat_id, voice=open(file_path, "rb"), caption=msg.content
                            )
                        elif media_type == "audio":
                            await self._app.bot.send_audio(
                                chat_id=chat_id, audio=open(file_path, "rb"), caption=msg.content
                            )
                        else:
                            await self._app.bot.send_document(
                                chat_id=chat_id, document=open(file_path, "rb"), caption=msg.content
                            )
                    finally:
                        if temp_path and temp_path.exists():
                            temp_path.unlink()

                # If we sent media, the content was likely sent as a caption.
                # If not, send it as a separate message.
                if not msg.content:
                    return

            # Send text message (Markdown V2 support could be added)
            # Standard Markdown is safer for general LLM output
            await self._app.bot.send_message(chat_id=chat_id, text=msg.content)

        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")

    def _start_typing(self, chat_id: int) -> None:
        """Start a background task to keep the typing indicator active."""
        self._stop_typing(chat_id)

        async def keep_typing():
            try:
                while self._running:
                    await self._app.bot.send_chat_action(chat_id=chat_id, action="typing")
                    await asyncio.sleep(4)
            except Exception:
                pass

        self._typing_tasks[chat_id] = asyncio.create_task(keep_typing())

    def _stop_typing(self, chat_id: int) -> None:
        """Stop the typing indicator task."""
        task = self._typing_tasks.pop(chat_id, None)
        if task:
            task.cancel()

    async def _on_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Log polling / handler errors instead of silently swallowing them."""
        logger.error(f"Telegram error: {context.error}")

    def _get_extension(self, media_type: str, mime_type: str | None) -> str:
        """Get file extension based on media type."""
        if media_type == "image":
            return ".jpg"
        if media_type == "voice":
            return ".ogg"
        if media_type == "audio":
            return ".mp3"
        return ".bin"
