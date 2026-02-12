"""Feishu/Lark channel implementation using lark-oapi SDK with WebSocket long connection."""

import asyncio
import json
import mimetypes
import re
import threading
import time
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.config.schema import FeishuConfig
from nanobot.channels.feishu_markdown import FeishuMarkdownConverter, should_render_markdown

try:
    import lark_oapi as lark
    from lark_oapi.api.cardkit.v1 import (
        ContentCardElementRequest,
        ContentCardElementRequestBody,
        CreateCardRequest,
        CreateCardRequestBody,
        SettingsCardRequest,
        SettingsCardRequestBody,
    )
    from lark_oapi.api.im.v1 import (
        CreateMessageReactionRequest,
        CreateMessageReactionRequestBody,
        CreateMessageRequest,
        CreateMessageRequestBody,
        Emoji,
        P2ImMessageReceiveV1,
        P2ImChatAccessEventBotP2pChatEnteredV1,
        P2ImMessageMessageReadV1,
        P2ImMessageReactionCreatedV1,
    )

    FEISHU_AVAILABLE = True
    CARDKIT_AVAILABLE = True
except ImportError:
    FEISHU_AVAILABLE = False
    CARDKIT_AVAILABLE = False
    lark = None
    Emoji = None

# Message type display mapping
MSG_TYPE_MAP = {
    "image": "[image]",
    "audio": "[audio]",
    "file": "[file]",
    "sticker": "[sticker]",
}

_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\((/[^)\s]+)\)")
_FILE_URI_RE = re.compile(r"\bfile:(/[^\s]+)")


class FeishuStreamingSession:
    """Manages a streaming card session using CardKit streaming API."""

    ELEMENT_ID = "streaming_content"  # Fixed element ID for streaming updates

    def __init__(self, client: Any, chat_id: str, receive_id_type: str):
        self.client = client
        self.chat_id = chat_id
        self.receive_id_type = receive_id_type
        self.card_id: str | None = None
        self.current_text = ""
        self.closed = False
        self.last_update_time = 0.0
        self.pending_text: str | None = None
        self._sequence = 0
        self._lock = threading.Lock()

    def _build_streaming_card_json(self, initial_text: str = "Thinking...") -> str:
        """Build Card JSON 2.0 with streaming mode enabled (no header for better preview)."""
        card = {
            "schema": "2.0",
            "config": {
                "streaming_mode": True,
                "summary": {"content": "[生成中...]"},
                "streaming_config": {
                    "print_frequency_ms": {"default": 50},
                    "print_step": {"default": 2},
                    "print_strategy": "fast",
                },
            },
            "body": {
                "elements": [
                    {
                        "tag": "markdown",
                        "content": initial_text,
                        "element_id": self.ELEMENT_ID,
                    }
                ]
            },
        }
        return json.dumps(card, ensure_ascii=False)

    def start_sync(self) -> bool:
        """Create card entity and send it (sync)."""
        if self.card_id:
            return True

        if not CARDKIT_AVAILABLE:
            logger.warning("CardKit API not available, falling back to simple mode")
            return False

        try:
            # Step 1: Create card entity with streaming mode
            card_json = self._build_streaming_card_json()
            create_request = (
                CreateCardRequest.builder()
                .request_body(
                    CreateCardRequestBody.builder().type("card_json").data(card_json).build()
                )
                .build()
            )

            create_response = self.client.cardkit.v1.card.create(create_request)
            if not create_response.success():
                logger.error(
                    f"Failed to create card entity: code={create_response.code}, "
                    f"msg={create_response.msg}. "
                    "Check if app has 'cardkit:card:write' permission."
                )
                return False

            self.card_id = create_response.data.card_id

            # Step 2: Send card entity as message
            msg_content = json.dumps(
                {"type": "card", "data": {"card_id": self.card_id}}, ensure_ascii=False
            )
            send_request = (
                CreateMessageRequest.builder()
                .receive_id_type(self.receive_id_type)
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(self.chat_id)
                    .msg_type("interactive")
                    .content(msg_content)
                    .build()
                )
                .build()
            )

            send_response = self.client.im.v1.message.create(send_request)
            if not send_response.success():
                logger.error(f"Failed to send card: {send_response.msg}")
                return False
            return True

        except Exception as e:
            logger.error(f"Error starting streaming session: {e}")
            return False

    def update_sync(self, text: str) -> bool:
        """Stream update text content using CardKit API (sync, with throttling)."""
        if self.closed or not self.card_id:
            return False

        with self._lock:
            now = time.time() * 1000
            # Throttle: max 10 requests/sec (100ms interval)
            if now - self.last_update_time < 100:
                self.pending_text = text  # Save for later
                return True  # Skip this update, will catch up

            self.pending_text = text
            self._sequence += 1
            seq = self._sequence
            self.current_text = text
            self.last_update_time = now

        try:
            # Use CardKit streaming content API
            # Each request needs a unique UUID for idempotency
            request = (
                ContentCardElementRequest.builder()
                .card_id(self.card_id)
                .element_id(self.ELEMENT_ID)
                .request_body(
                    ContentCardElementRequestBody.builder()
                    .content(text)
                    .uuid(str(uuid.uuid4()))  # New UUID for each request
                    .sequence(seq)
                    .build()
                )
                .build()
            )

            response = self.client.cardkit.v1.card_element.content(request)
            return response.success()
        except Exception:
            return False

    def close_sync(self, final_text: str | None = None) -> bool:
        """Close streaming mode and finalize card (sync)."""
        if self.closed:
            return True
        self.closed = True

        if not self.card_id:
            return False

        text = final_text or self.pending_text or self.current_text or "Done."

        try:
            # Final content update
            with self._lock:
                self._sequence += 1
                seq = self._sequence

            content_request = (
                ContentCardElementRequest.builder()
                .card_id(self.card_id)
                .element_id(self.ELEMENT_ID)
                .request_body(
                    ContentCardElementRequestBody.builder()
                    .content(text)
                    .uuid(str(uuid.uuid4()))
                    .sequence(seq)
                    .build()
                )
                .build()
            )
            self.client.cardkit.v1.card_element.content(content_request)

            # Close streaming mode and clear summary (removes "[生成中...]")
            settings = {"config": {"streaming_mode": False, "summary": {"content": ""}}}
            settings_request = (
                SettingsCardRequest.builder()
                .card_id(self.card_id)
                .request_body(
                    SettingsCardRequestBody.builder()
                    .settings(json.dumps(settings, ensure_ascii=False))
                    .uuid(str(uuid.uuid4()))
                    .sequence(seq + 1)
                    .build()
                )
                .build()
            )

            resp = self.client.cardkit.v1.card.settings(settings_request)
            if not resp.success():
                logger.warning(f"Failed to close streaming: {resp.code} {resp.msg}")
            return resp.success()
        except Exception as e:
            logger.error(f"Error closing streaming session: {e}")
            return False


class FeishuChannel(BaseChannel):
    """
    Feishu/Lark channel using WebSocket long connection.

    Uses WebSocket to receive events - no public IP or webhook required.

    Requires:
    - App ID and App Secret from Feishu Open Platform
    - Bot capability enabled
    - Event subscription enabled (im.message.receive_v1)
    """

    name = "feishu"

    def __init__(
        self,
        config: FeishuConfig,
        bus: MessageBus,
        *,
        attachment_base_dir: Path | None = None,
        attachment_allowed_dir: Path | None = None,
    ):
        super().__init__(config, bus)
        self.config: FeishuConfig = config
        self._client: Any = None
        self._ws_client: Any = None
        self._ws_thread: threading.Thread | None = None
        self._processed_message_ids: OrderedDict[str, None] = OrderedDict()  # Ordered dedup cache
        self._loop: asyncio.AbstractEventLoop | None = None
        self._markdown_converter: FeishuMarkdownConverter | None = None
        self._attachment_base_dir = attachment_base_dir
        self._attachment_allowed_dir = attachment_allowed_dir
        if self.config.render_markdown:
            self._markdown_converter = FeishuMarkdownConverter()
        self._tenant_access_token: str | None = None
        self._token_expire_at: float = 0.0

    @staticmethod
    def _extract_explicit_attachments(text: str) -> tuple[str, list[str]]:
        attachments: list[str] = []

        def replace_md(match: re.Match[str]) -> str:
            attachments.append(match.group(1))
            return ""

        def replace_file(match: re.Match[str]) -> str:
            attachments.append(match.group(1))
            return ""

        cleaned = _MD_IMAGE_RE.sub(replace_md, text)
        cleaned = _FILE_URI_RE.sub(replace_file, cleaned)
        return cleaned.strip(), attachments

    @staticmethod
    def _normalize_attachment_paths(
        paths: list[str],
        base_dir: Path | None = None,
        allowed_dir: Path | None = None,
    ) -> list[Path]:
        normalized: list[Path] = []
        seen: set[str] = set()
        base = (base_dir or allowed_dir or Path.cwd()).expanduser().resolve()
        allowed_root = allowed_dir.expanduser().resolve() if allowed_dir else None
        for raw in paths:
            if not isinstance(raw, str) or raw in seen:
                continue
            seen.add(raw)
            path = Path(raw).expanduser()
            resolved = path if path.is_absolute() else base / path
            resolved = resolved.resolve()
            if allowed_root and not resolved.is_relative_to(allowed_root):
                continue
            if resolved.is_file():
                normalized.append(resolved)
        return normalized

    async def _get_tenant_access_token(self) -> str | None:
        now = time.time()
        if self._tenant_access_token and now < self._token_expire_at:
            return self._tenant_access_token

        token_url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        payload = {
            "app_id": self.config.app_id,
            "app_secret": self.config.app_secret,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(token_url, json=payload)
            if response.status_code != 200:
                logger.error(f"Failed to get access token: status {response.status_code}")
                return None
            data = response.json()
            if data.get("code") != 0:
                logger.error(f"Failed to get access token: {data.get('msg')}")
                return None
            token = data.get("tenant_access_token")
            expire = data.get("expire", 0)
            if not token:
                logger.error("Failed to get access token: missing token")
                return None
            # refresh slightly early
            self._tenant_access_token = token
            self._token_expire_at = now + max(0, int(expire) - 60)
            return token

    async def _upload_image_http(self, path: Path) -> str | None:
        token = await self._get_tenant_access_token()
        if not token:
            return None

        api_url = "https://open.feishu.cn/open-apis/im/v1/images"
        headers = {"Authorization": f"Bearer {token}"}
        try:
            with path.open("rb") as f:
                files = {"image": (path.name, f)}
                data = {"image_type": "message"}
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(api_url, headers=headers, data=data, files=files)
            if response.status_code != 200:
                logger.warning(
                    f"Image upload failed: status={response.status_code}, body={response.text[:500]}"
                )
                return None
            payload = response.json()
            if payload.get("code") != 0:
                logger.warning(f"Image upload error: {payload.get('msg')}")
                return None
            return payload.get("data", {}).get("image_key")
        except Exception as e:
            logger.error(f"Image upload error: {e}")
            return None

    async def _upload_file_http(self, path: Path) -> str | None:
        token = await self._get_tenant_access_token()
        if not token:
            return None

        api_url = "https://open.feishu.cn/open-apis/im/v1/files"
        headers = {"Authorization": f"Bearer {token}"}
        try:
            with path.open("rb") as f:
                files = {"file": (path.name, f)}
                data = {"file_type": "stream", "file_name": path.name}
                async with httpx.AsyncClient(timeout=120.0) as client:
                    response = await client.post(api_url, headers=headers, data=data, files=files)
            if response.status_code != 200:
                logger.warning(
                    f"File upload failed: status={response.status_code}, body={response.text[:500]}"
                )
                return None
            payload = response.json()
            if payload.get("code") != 0:
                logger.warning(f"File upload error: {payload.get('msg')}")
                return None
            return payload.get("data", {}).get("file_key")
        except Exception as e:
            logger.error(f"File upload error: {e}")
            return None

    async def start(self) -> None:
        """Start the Feishu bot with WebSocket long connection."""
        if not FEISHU_AVAILABLE:
            logger.error("Feishu SDK not installed. Run: pip install lark-oapi")
            return

        if not self.config.app_id or not self.config.app_secret:
            logger.error("Feishu app_id and app_secret not configured")
            return

        self._running = True
        self._loop = asyncio.get_running_loop()

        # Create Lark client for sending messages
        self._client = (
            lark.Client.builder()
            .app_id(self.config.app_id)
            .app_secret(self.config.app_secret)
            .log_level(lark.LogLevel.INFO)
            .build()
        )

        # Create event handler (register message receive and other common events)
        event_handler = (
            lark.EventDispatcherHandler.builder(
                self.config.encrypt_key or "",
                self.config.verification_token or "",
            )
            .register_p2_im_message_receive_v1(self._on_message_sync)
            .register_p2_im_message_reaction_created_v1(self._on_reaction_created)
            .register_p2_im_chat_access_event_bot_p2p_chat_entered_v1(
                self._on_p2p_chat_entered_sync
            )
            .register_p2_im_message_message_read_v1(self._on_message_read_sync)
            .build()
        )
        # Create WebSocket client for long connection
        self._ws_client = lark.ws.Client(
            self.config.app_id,
            self.config.app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.INFO,
        )

        # Start WebSocket client in a separate thread
        def run_ws():
            try:
                self._ws_client.start()
            except Exception as e:
                logger.error(f"Feishu WebSocket error: {e}")

        self._ws_thread = threading.Thread(target=run_ws, daemon=True)
        self._ws_thread.start()

        logger.info("Feishu bot started with WebSocket long connection")
        logger.info("No public IP required - using WebSocket to receive events")

        # Keep running until stopped
        while self._running:
            await asyncio.sleep(1)

    async def stop(self) -> None:
        """Stop the Feishu bot."""
        self._running = False
        if self._ws_client:
            try:
                self._ws_client.stop()
            except Exception as e:
                logger.warning(f"Error stopping WebSocket client: {e}")
        logger.info("Feishu bot stopped")

    async def _add_reaction(self, message_id: str, emoji_type: str = "THUMBSUP") -> None:
        """Add a reaction emoji to a message (non-blocking)."""
        if not self._client or not Emoji:
            return

        def add_sync():
            try:
                request = (
                    CreateMessageReactionRequest.builder()
                    .message_id(message_id)
                    .request_body(
                        CreateMessageReactionRequestBody.builder()
                        .reaction_type(Emoji.builder().emoji_type(emoji_type).build())
                        .build()
                    )
                    .build()
                )
                self._client.im.v1.message_reaction.create(request)
            except Exception:
                pass

        await asyncio.get_running_loop().run_in_executor(None, add_sync)

    async def _download_media(self, message_id: str, file_key: str, media_type: str) -> str | None:
        """
        Download media file from Feishu and save to local disk.

        Args:
            message_id: Message ID
            file_key: File key (image_key or file_key)
            media_type: Media type (image/audio/file)

        Returns:
            Local file path, or None if download failed
        """
        try:
            # Get file extension
            ext = self._get_extension(media_type)

            # Create media directory
            from nanobot.utils.helpers import get_data_path
            media_dir = get_data_path() / "media"
            media_dir.mkdir(parents=True, exist_ok=True)

            # Generate file path
            file_path = media_dir / f"{file_key[:16]}{ext}"

            # Fetch file content from Feishu API
            file_content = await self._fetch_file_content(message_id, file_key, media_type)

            if not file_content:
                logger.warning(f"Failed to fetch {media_type} content: {file_key}")
                return None

            # Save to file
            file_path.write_bytes(file_content)

            logger.info(f"Downloaded {media_type} to {file_path}")
            return str(file_path)

        except Exception as e:
            logger.error(f"Failed to download {media_type}: {e}")
            return None

    async def _fetch_file_content(self, message_id: str, file_key: str, media_type: str) -> bytes | None:
        """
        Fetch file content from Feishu API.

        Uses message resource API to get file content directly.

        Returns:
            File content as bytes, or None if failed
        """
        try:
            # Get tenant access token via HTTP API
            token_url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
            token_payload = {
                "app_id": self.config.app_id,
                "app_secret": self.config.app_secret
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                token_response = await client.post(token_url, json=token_payload)

                if token_response.status_code != 200:
                    logger.error(f"Failed to get access token: status {token_response.status_code}")
                    return None

                token_data = token_response.json()
                if token_data.get("code") != 0:
                    logger.error(f"Failed to get access token: {token_data.get('msg')}")
                    return None

                access_token = token_data.get("tenant_access_token")
                logger.debug(f"Got access token: {access_token[:20]}...")

                # Use message resource API to get file content
                # Reference: https://open.feishu.cn/document/server-docs/im-v1/message-resource/get
                api_url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/resources/{file_key}"

                # Make request to get file
                response = await client.get(
                    api_url,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                    },
                    params={"type": media_type}
                )

                logger.debug(f"Fetch file response: status={response.status_code}")
                logger.debug(f"Response headers: {dict(response.headers)}")
                logger.debug(f"Response content-type: {response.headers.get('Content-Type', 'unknown')}")

                if response.status_code != 200:
                    logger.warning(f"HTTP error: status={response.status_code}, response={response.text[:500]}")
                    return None

                # Check if response is JSON (might contain download_url or file data)
                content_type = response.headers.get("Content-Type", "")

                if "application/json" in content_type:
                    try:
                        data = response.json()
                        logger.debug(f"JSON response: {json.dumps(data, ensure_ascii=False)}")

                        if data.get("code") == 0:
                            # Check if response contains download_url
                            download_url = data.get("data", {}).get("file", {}).get("download_url")
                            if download_url:
                                # Download from the URL
                                logger.info(f"Got download URL, fetching from: {download_url}")
                                file_resp = await client.get(download_url)
                                file_resp.raise_for_status()
                                return file_resp.content

                            # Check if response contains file content (base64 or other format)
                            file_data = data.get("data", {}).get("file", {}).get("content")
                            if file_data:
                                import base64
                                return base64.b64decode(file_data)

                            logger.error(f"JSON response doesn't contain file content or download_url")
                        else:
                            logger.error(f"API error: code={data.get('code')}, msg={data.get('msg')}")
                        return None
                    except Exception as json_err:
                        logger.error(f"Failed to parse JSON response: {json_err}")
                        logger.error(f"Response was: {response.text[:1000]}")
                        return None

                # Response is binary file content directly
                logger.info(f"Got binary file content, size: {len(response.content)} bytes")
                return response.content

        except Exception as e:
            logger.error(f"Error fetching file content: {e}")
            return None

    def _get_extension(self, media_type: str) -> str:
        """Get file extension based on media type."""
        ext_map = {
            "image": ".jpg",
            "audio": ".m4a",
            "file": "",
            "video": ".mp4",
        }
        return ext_map.get(media_type, "")
    # Regex to match markdown tables (header + separator + data rows)
    _TABLE_RE = re.compile(
        r"((?:^[ \t]*\|.+\|[ \t]*\n)(?:^[ \t]*\|[-:\s|]+\|[ \t]*\n)(?:^[ \t]*\|.+\|[ \t]*\n?)+)",
        re.MULTILINE,
    )

    @staticmethod
    def _parse_md_table(table_text: str) -> dict | None:
        """Parse a markdown table into a Feishu table element."""
        lines = [line.strip() for line in table_text.strip().split("\n") if line.strip()]
        if len(lines) < 3:
            return None

        def split_row(row: str) -> list[str]:
            return [c.strip() for c in row.strip("|").split("|")]

        headers = split_row(lines[0])
        rows = [split_row(row) for row in lines[2:]]
        columns = [
            {"tag": "column", "name": f"c{i}", "display_name": h, "width": "auto"}
            for i, h in enumerate(headers)
        ]
        return {
            "tag": "table",
            "page_size": len(rows) + 1,
            "columns": columns,
            "rows": [
                {f"c{i}": r[i] if i < len(r) else "" for i in range(len(headers))} for r in rows
            ],
        }

    def _build_card_elements(self, content: str) -> list[dict]:
        """Split content into markdown + table elements for Feishu card."""
        elements, last_end = [], 0
        for m in self._TABLE_RE.finditer(content):
            before = content[last_end : m.start()].strip()
            if before:
                elements.append({"tag": "markdown", "content": before})
            elements.append(
                self._parse_md_table(m.group(1)) or {"tag": "markdown", "content": m.group(1)}
            )
            last_end = m.end()
        remaining = content[last_end:].strip()
        if remaining:
            elements.append({"tag": "markdown", "content": remaining})
        return elements or [{"tag": "markdown", "content": content}]

    @staticmethod
    def _guess_is_image(path: Path) -> bool:
        mime, _ = mimetypes.guess_type(path.as_posix())
        return bool(mime and mime.startswith("image/"))

    async def _send_image(self, receive_id_type: str, receive_id: str, image_key: str) -> None:
        request = CreateMessageRequest.builder() \
            .receive_id_type(receive_id_type) \
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(receive_id)
                .msg_type("image")
                .content(json.dumps({"image_key": image_key}))
                .build()
            ).build()
        response = self._client.im.v1.message.create(request)
        if not response.success():
            logger.warning(
                f"Failed to send Feishu image: code={response.code}, msg={response.msg}, "
                f"log_id={response.get_log_id()}"
            )

    async def _send_file(self, receive_id_type: str, receive_id: str, file_key: str) -> None:
        request = CreateMessageRequest.builder() \
            .receive_id_type(receive_id_type) \
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(receive_id)
                .msg_type("file")
                .content(json.dumps({"file_key": file_key}))
                .build()
            ).build()
        response = self._client.im.v1.message.create(request)
        if not response.success():
            logger.warning(
                f"Failed to send Feishu file: code={response.code}, msg={response.msg}, "
                f"log_id={response.get_log_id()}"
            )

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message through Feishu."""
        if not self._client:
            logger.warning("Feishu client not initialized")
            return

        try:
            # Determine receive_id_type based on chat_id format
            # open_id starts with "ou_", chat_id starts with "oc_"
            if msg.chat_id.startswith("oc_"):
                receive_id_type = "chat_id"
            else:
                receive_id_type = "open_id"

            cleaned_text, extracted = self._extract_explicit_attachments(msg.content)
            attachments: list[str] = []
            if msg.media:
                attachments.extend(msg.media)
            if extracted:
                attachments.extend(extracted)

            normalized = self._normalize_attachment_paths(
                attachments,
                base_dir=self._attachment_base_dir,
                allowed_dir=self._attachment_allowed_dir,
            )

            if cleaned_text.strip():
                msg_type = "text"
                content = json.dumps({"text": cleaned_text})

                if self.config.render_markdown:
                    if self._TABLE_RE.search(cleaned_text):
                        elements = self._build_card_elements(cleaned_text)
                        card = {
                            "config": {"wide_screen_mode": True},
                            "elements": elements,
                        }
                        msg_type = "interactive"
                        content = json.dumps(card, ensure_ascii=False)
                    elif self._markdown_converter and should_render_markdown(cleaned_text):
                        msg_type = "post"
                        post_content = self._markdown_converter.convert(cleaned_text)
                        content = json.dumps(post_content)

                request = CreateMessageRequest.builder() \
                    .receive_id_type(receive_id_type) \
                    .request_body(
                        CreateMessageRequestBody.builder()
                        .receive_id(msg.chat_id)
                        .msg_type(msg_type)
                        .content(content)
                        .build()
                    ).build()

                response = self._client.im.v1.message.create(request)

                if not response.success():
                    logger.error(
                        f"Failed to send Feishu message: code={response.code}, "
                        f"msg={response.msg}, log_id={response.get_log_id()}"
                    )
                else:
                    logger.debug(f"Feishu message sent to {msg.chat_id} (type={msg_type})")

            for path in normalized:
                try:
                    size = path.stat().st_size
                    if self._guess_is_image(path):
                        if size > 10 * 1024 * 1024:
                            logger.warning(f"Image too large (>10MB): {path}")
                            continue
                        image_key = await self._upload_image_http(path)
                        if image_key:
                            await self._send_image(receive_id_type, msg.chat_id, image_key)
                        else:
                            logger.warning(f"Image upload failed: {path}")
                    else:
                        if size > 30 * 1024 * 1024:
                            logger.warning(f"File too large (>30MB): {path}")
                            continue
                        file_key = await self._upload_file_http(path)
                        if file_key:
                            await self._send_file(receive_id_type, msg.chat_id, file_key)
                        else:
                            logger.warning(f"File upload failed: {path}")
                except Exception as e:
                    logger.error(f"Error sending attachment {path}: {e}")

        except Exception as e:
            logger.error(f"Error sending Feishu message: {e}")

    def _on_message_sync(self, data: "P2ImMessageReceiveV1") -> None:
        """
        Sync handler for incoming messages (called from WebSocket thread).
        Schedules async handling in the main event loop.
        """
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._on_message(data), self._loop)

    def _on_p2p_chat_entered_sync(self, data: "P2ImChatAccessEventBotP2pChatEnteredV1") -> None:
        """
        Sync handler for p2p chat entered event.
        Just logs the event to avoid "processor not found" errors.
        """
        try:
            event = data.event
            operator_id = event.operator_ids.open_id if event.operator_ids else "unknown"
            logger.debug(f"User {operator_id} entered P2P chat with bot")
        except Exception as e:
            logger.debug(f"Error handling p2p chat entered event: {e}")

    def _on_message_read_sync(self, data: "P2ImMessageMessageReadV1") -> None:
        """
        Sync handler for message read event.
        Just logs the event to avoid "processor not found" errors.
        """
        try:
            event = data.event
            reader_id = event.reader.reader_id.open_id if event.reader and event.reader.reader_id else "unknown"
            logger.debug(f"User {reader_id} read messages: {event.message_id_list}")
        except Exception as e:
            logger.debug(f"Error handling message read event: {e}")

    async def _on_message(self, data: "P2ImMessageReceiveV1") -> None:
        """Handle incoming message from Feishu with streaming support."""
        try:
            event = data.event
            message = event.message
            sender = event.sender

            # Deduplication check
            message_id = message.message_id
            if message_id in self._processed_message_ids:
                return
            self._processed_message_ids[message_id] = None

            # Trim cache: keep most recent 500 when exceeds 1000
            while len(self._processed_message_ids) > 1000:
                self._processed_message_ids.popitem(last=False)

            # Skip bot messages
            sender_type = sender.sender_type
            if sender_type == "bot":
                return

            sender_id = sender.sender_id.open_id if sender.sender_id else "unknown"
            chat_id = message.chat_id
            chat_type = message.chat_type  # "p2p" or "group"
            msg_type = message.message_type

            # Add reaction to indicate "seen"
            if self.config.reaction_emoji:
                await self._add_reaction(message_id, self.config.reaction_emoji)

            # Parse message content and handle media
            content_parts: list[str] = []
            media_paths: list[str] = []
            if msg_type == "text":
                try:
                    content = json.loads(message.content).get("text", "")
                except json.JSONDecodeError:
                    content = message.content or ""
                content_parts.append(content)

            elif msg_type in ("image", "audio", "file", "video"):
                # Download media file
                try:
                    content_json = json.loads(message.content)
                    logger.debug(f"Media content: {content_json}")

                    # Get file key (different keys for different types)
                    file_key = None
                    if msg_type == "image":
                        file_key = content_json.get("image_key")
                    else:
                        file_key = content_json.get("file_key")

                    logger.info(f"Processing {msg_type}: file_key={file_key}, message_id={message_id}")

                    if file_key:
                        # Download the file
                        local_path = await self._download_media(
                            message_id=message_id,
                            file_key=file_key,
                            media_type=msg_type
                        )

                        if local_path:
                            media_paths.append(local_path)
                            content_parts.append(f"[{msg_type}: {local_path}]")
                            logger.info(f"Successfully downloaded {msg_type} to {local_path}")
                        else:
                            content_parts.append(f"[{msg_type}: download failed]")
                            logger.warning(f"Failed to download {msg_type}")
                    else:
                        content_parts.append(f"[{msg_type}: no file_key]")
                        logger.warning(f"No file_key found for {msg_type}")

                except json.JSONDecodeError:
                    content_parts.append(f"[{msg_type}: JSON decode error]")
                    logger.error(f"JSON decode error for {msg_type}")
                except Exception as e:
                    logger.error(f"Error processing media: {e}")
                    content_parts.append(f"[{msg_type}: processing error]")
            else:
                # Other message types
                content_parts.append(MSG_TYPE_MAP.get(msg_type, f"[{msg_type}]"))

            # Build final content
            content = "\n".join(content_parts) if content_parts else ""

            if not content:
                return

            # Determine reply target
            reply_to = chat_id if chat_type == "group" else sender_id
            receive_id_type = "chat_id" if reply_to.startswith("oc_") else "open_id"

            # Check permission first
            if not self.is_allowed(sender_id):
                logger.warning(
                    f"Access denied for sender {sender_id} on channel {self.name}. "
                    f"Add them to allowFrom list in config to grant access."
                )
                return

            # Try to create streaming session
            stream_id = str(uuid.uuid4())
            streaming_session: FeishuStreamingSession | None = None
            use_streaming = False
            loop = asyncio.get_running_loop()

            # Check if streaming is enabled in config and CardKit is available
            if self.config.streaming and CARDKIT_AVAILABLE:
                streaming_session = FeishuStreamingSession(
                    client=self._client, chat_id=reply_to, receive_id_type=receive_id_type
                )
                use_streaming = await loop.run_in_executor(None, streaming_session.start_sync)
                if not use_streaming:
                    streaming_session = None

            if use_streaming and streaming_session:
                # Accumulated text for updates
                accumulated_text = ""
                accumulated_lock = threading.Lock()

                def stream_callback(chunk: str) -> None:
                    """Callback invoked for each streaming chunk (non-blocking)."""
                    nonlocal accumulated_text
                    with accumulated_lock:
                        accumulated_text += chunk
                        text_snapshot = accumulated_text
                    # Submit update to thread pool (fire-and-forget)
                    try:
                        loop.run_in_executor(None, streaming_session.update_sync, text_snapshot)
                    except RuntimeError:
                        # Loop might be closed
                        pass

                # Register callback with bus
                self.bus.register_stream_callback(stream_id, stream_callback)

            # Create and publish inbound message
            msg = InboundMessage(
                channel=self.name,
                sender_id=str(sender_id),
                chat_id=str(reply_to),
                content=content,
                media=media_paths,
                metadata={
                    "message_id": message_id,
                    "chat_type": chat_type,
                    "msg_type": msg_type,
                },
                stream_id=stream_id if use_streaming else None,
            )

            await self.bus.publish_inbound(msg)

            # Wait for response and close streaming session if active
            if use_streaming and streaming_session:
                await self._wait_and_close_stream(streaming_session, stream_id)

        except Exception as e:
            logger.error(f"Error processing Feishu message: {e}")

    def _on_reaction_created(self, data: "P2ImMessageReactionCreatedV1") -> None:
        """
        Handler for message reaction events.
        We don't need to process these, but registering prevents error logs.
        """
        pass

    async def _wait_and_close_stream(
        self, session: "FeishuStreamingSession", stream_id: str
    ) -> None:
        """Wait for agent loop to finish, then close streaming session."""
        loop = asyncio.get_running_loop()

        # Wait for agent loop to signal completion (via bus.mark_stream_done)
        await self.bus.wait_stream_done(stream_id, timeout=300)

        if not session.closed:
            await loop.run_in_executor(
                None, session.close_sync, session.pending_text or session.current_text
            )
