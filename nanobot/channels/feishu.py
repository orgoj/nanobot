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
from nanobot.channels.feishu_markdown import FeishuMarkdownConverter, should_render_markdown
from nanobot.config.schema import FeishuConfig

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
        P2ImChatAccessEventBotP2pChatEnteredV1,
        P2ImMessageMessageReadV1,
        P2ImMessageReactionCreatedV1,
        P2ImMessageReceiveV1,
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
        """Build Card JSON 2.0 with streaming mode enabled."""
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
            logger.warning("CardKit API not available")
            return False

        try:
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
                logger.error(f"Failed to create card entity: {create_response.msg}")
                return False

            self.card_id = create_response.data.card_id

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
        """Stream update text content."""
        if self.closed or not self.card_id:
            return False

        with self._lock:
            now = time.time() * 1000
            if now - self.last_update_time < 100:
                self.pending_text = text
                return True

            self.pending_text = text
            self._sequence += 1
            seq = self._sequence
            self.current_text = text
            self.last_update_time = now

        try:
            request = (
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
            response = self.client.cardkit.v1.card_element.content(request)
            return response.success()
        except Exception:
            return False

    def close_sync(self, final_text: str | None = None) -> bool:
        """Close streaming mode and finalize card."""
        if self.closed:
            return True
        self.closed = True

        if not self.card_id:
            return False

        text = final_text or self.pending_text or self.current_text or "Done."

        try:
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
            return resp.success()
        except Exception as e:
            logger.error(f"Error closing streaming session: {e}")
            return False


class FeishuChannel(BaseChannel):
    """Feishu/Lark channel using WebSocket long connection."""

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
        self._processed_message_ids: OrderedDict[str, None] = OrderedDict()
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
            resolved = (path if path.is_absolute() else base / path).resolve()
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
        payload = {"app_id": self.config.app_id, "app_secret": self.config.app_secret}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(token_url, json=payload)
            if response.status_code != 200:
                return None
            data = response.json()
            if data.get("code") != 0:
                return None
            token = data.get("tenant_access_token")
            self._tenant_access_token = token
            self._token_expire_at = now + max(0, int(data.get("expire", 0)) - 60)
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
                return None
            payload = response.json()
            return payload.get("data", {}).get("image_key") if payload.get("code") == 0 else None
        except Exception:
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
                return None
            payload = response.json()
            return payload.get("data", {}).get("file_key") if payload.get("code") == 0 else None
        except Exception:
            return None

    async def start(self) -> None:
        """Start the Feishu bot."""
        if not FEISHU_AVAILABLE:
            logger.error("Feishu SDK not installed")
            return
        if not self.config.app_id or not self.config.app_secret:
            logger.error("Feishu not configured")
            return

        self._running = True
        self._loop = asyncio.get_running_loop()
        self._client = lark.Client.builder().app_id(self.config.app_id).app_secret(self.config.app_secret).build()

        event_handler = (
            lark.EventDispatcherHandler.builder(self.config.encrypt_key or "", self.config.verification_token or "")
            .register_p2_im_message_receive_v1(self._on_message_sync)
            .register_p2_im_message_reaction_created_v1(self._on_reaction_created)
            .register_p2_im_chat_access_event_bot_p2p_chat_entered_v1(self._on_p2p_chat_entered_sync)
            .register_p2_im_message_message_read_v1(self._on_message_read_sync)
            .build()
        )
        self._ws_client = lark.ws.Client(self.config.app_id, self.config.app_secret, event_handler=event_handler)

        def run_ws():
            while self._running:
                try:
                    self._ws_client.start()
                except Exception:
                    pass
                if self._running:
                    time.sleep(5)

        self._ws_thread = threading.Thread(target=run_ws, daemon=True)
        self._ws_thread.start()
        logger.info("Feishu bot started via WebSocket")
        while self._running:
            await asyncio.sleep(1)

    async def stop(self) -> None:
        self._running = False
        if self._ws_client:
            self._ws_client.stop()
        logger.info("Feishu bot stopped")

    async def _add_reaction(self, message_id: str, emoji_type: str = "THUMBSUP") -> None:
        if not self._client or not Emoji:
            return

        def add_sync():
            try:
                request = CreateMessageReactionRequest.builder().message_id(message_id).request_body(
                    CreateMessageReactionRequestBody.builder().reaction_type(Emoji.builder().emoji_type(emoji_type).build()).build()
                ).build()
                self._client.im.v1.message_reaction.create(request)
            except Exception:
                pass
        await asyncio.get_running_loop().run_in_executor(None, add_sync)

    async def _download_media(self, message_id: str, file_key: str, media_type: str) -> str | None:
        try:
            from nanobot.utils.helpers import get_data_path
            ext = {"image": ".jpg", "audio": ".m4a", "file": "", "video": ".mp4"}.get(media_type, "")
            media_dir = get_data_path() / "media"
            media_dir.mkdir(parents=True, exist_ok=True)
            file_path = media_dir / f"{file_key[:16]}{ext}"
            file_content = await self._fetch_file_content(message_id, file_key, media_type)
            if not file_content:
                return None
            file_path.write_bytes(file_content)
            return str(file_path)
        except Exception:
            return None

    async def _fetch_file_content(self, message_id: str, file_key: str, media_type: str) -> bytes | None:
        try:
            token = await self._get_tenant_access_token()
            if not token:
                return None
            api_url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/resources/{file_key}"
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(api_url, headers={"Authorization": f"Bearer {token}"}, params={"type": media_type})
                if response.status_code != 200:
                    return None
                if "application/json" in response.headers.get("Content-Type", ""):
                    data = response.json()
                    if data.get("code") == 0:
                        url = data.get("data", {}).get("file", {}).get("download_url")
                        if url:
                            r = await client.get(url)
                            return r.content
                    return None
                return response.content
        except Exception:
            return None

    _TABLE_RE = re.compile(r"((?:^[ \t]*\|.+\|[ \t]*\n)(?:^[ \t]*\|[-:\s|]+\|[ \t]*\n)(?:^[ \t]*\|.+\|[ \t]*\n?)+)", re.MULTILINE)

    @staticmethod
    def _parse_md_table(table_text: str) -> dict | None:
        lines = [line.strip() for line in table_text.strip().split("\n") if line.strip()]
        if len(lines) < 3:
            return None
        headers = [c.strip() for c in lines[0].strip("|").split("|")]
        rows = [[c.strip() for c in line.strip("|").split("|")] for line in lines[2:]]
        columns = [{"tag": "column", "name": f"c{i}", "display_name": h, "width": "auto"} for i, h in enumerate(headers)]
        return {"tag": "table", "page_size": len(rows) + 1, "columns": columns, "rows": [{f"c{i}": r[i] if i < len(r) else "" for i in range(len(headers))} for r in rows]}

    def _build_card_elements(self, content: str) -> list[dict]:
        elements, last_end = [], 0
        for m in self._TABLE_RE.finditer(content):
            if before := content[last_end : m.start()].strip():
                elements.append({"tag": "markdown", "content": before})
            elements.append(self._parse_md_table(m.group(1)) or {"tag": "markdown", "content": m.group(1)})
            last_end = m.end()
        if remaining := content[last_end:].strip():
            elements.append({"tag": "markdown", "content": remaining})
        return elements or [{"tag": "markdown", "content": content}]

    async def send(self, msg: OutboundMessage) -> None:
        if not self._client:
            return
        try:
            receive_id_type = "chat_id" if msg.chat_id.startswith("oc_") else "open_id"
            cleaned_text, extracted = self._extract_explicit_attachments(msg.content)
            attachments = (msg.media or []) + extracted
            normalized = self._normalize_attachment_paths(attachments, base_dir=self._attachment_base_dir, allowed_dir=self._attachment_allowed_dir)
            if cleaned_text.strip():
                msg_type, content = "text", json.dumps({"text": cleaned_text})
                if self.config.render_markdown:
                    if self._TABLE_RE.search(cleaned_text):
                        msg_type, content = "interactive", json.dumps({"config": {"wide_screen_mode": True}, "elements": self._build_card_elements(cleaned_text)}, ensure_ascii=False)
                    elif self._markdown_converter and should_render_markdown(cleaned_text):
                        msg_type, content = "post", json.dumps(self._markdown_converter.convert(cleaned_text))
                request = CreateMessageRequest.builder().receive_id_type(receive_id_type).request_body(
                    CreateMessageRequestBody.builder().receive_id(msg.chat_id).msg_type(msg_type).content(content).build()
                ).build()
                self._client.im.v1.message.create(request)
            for path in normalized:
                try:
                    if mimetypes.guess_type(path.as_posix())[0].startswith("image/"):
                        if (key := await self._upload_image_http(path)):
                            self._client.im.v1.message.create(CreateMessageRequest.builder().receive_id_type(receive_id_type).request_body(
                                CreateMessageRequestBody.builder().receive_id(msg.chat_id).msg_type("image").content(json.dumps({"image_key": key})).build()).build())
                    else:
                        if (key := await self._upload_file_http(path)):
                            self._client.im.v1.message.create(CreateMessageRequest.builder().receive_id_type(receive_id_type).request_body(
                                CreateMessageRequestBody.builder().receive_id(msg.chat_id).msg_type("file").content(json.dumps({"file_key": key})).build()).build())
                except Exception:
                    pass
        except Exception:
            pass

    def _on_message_sync(self, data: "P2ImMessageReceiveV1") -> None:
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(lambda: asyncio.create_task(self._on_message(data)))

    def _on_p2p_chat_entered_sync(self, data: "P2ImChatAccessEventBotP2pChatEnteredV1") -> None:
        pass

    def _on_message_read_sync(self, data: "P2ImMessageMessageReadV1") -> None:
        pass

    def _on_reaction_created(self, data: "P2ImMessageReactionCreatedV1") -> None:
        pass

    async def _on_message(self, data: "P2ImMessageReceiveV1") -> None:
        try:
            event = data.event
            message, sender = event.message, event.sender
            if message.message_id in self._processed_message_ids or sender.sender_type == "bot":
                return
            self._processed_message_ids[message.message_id] = None
            while len(self._processed_message_ids) > 1000:
                self._processed_message_ids.popitem(last=False)
            if self.config.reaction_emoji:
                await self._add_reaction(message.message_id, self.config.reaction_emoji)
            sender_id = sender.sender_id.open_id if sender.sender_id else "unknown"
            if not self.is_allowed(sender_id):
                return
            content_parts, media_paths = [], []
            if message.message_type == "text":
                try:
                    content_parts.append(json.loads(message.content).get("text", ""))
                except Exception:
                    content_parts.append(message.content or "")
            elif message.message_type in ("image", "audio", "file", "video"):
                try:
                    c = json.loads(message.content)
                    key = c.get("image_key") if message.message_type == "image" else c.get("file_key")
                    if key and (p := await self._download_media(message.message_id, key, message.message_type)):
                        media_paths.append(p)
                        content_parts.append(f"[{message.message_type}: {p}]")
                except Exception:
                    pass
            else:
                content_parts.append(MSG_TYPE_MAP.get(message.message_type, f"[{message.message_type}]"))
            content = "\n".join(content_parts).strip()
            if not content:
                return
            reply_to = message.chat_id if message.chat_type == "group" else sender_id
            stream_id, streaming_session, use_streaming = str(uuid.uuid4()), None, False
            if self.config.streaming and CARDKIT_AVAILABLE:
                streaming_session = FeishuStreamingSession(self._client, reply_to, "chat_id" if reply_to.startswith("oc_") else "open_id")
                use_streaming = await self._loop.run_in_executor(None, streaming_session.start_sync)
            if use_streaming and streaming_session:
                acc_text, acc_lock = "", threading.Lock()

                def cb(chunk: str):
                    nonlocal acc_text
                    with acc_lock:
                        acc_text += chunk
                        t = acc_text
                    try:
                        self._loop.run_in_executor(None, streaming_session.update_sync, t)
                    except Exception:
                        pass
                self.bus.register_stream_callback(stream_id, cb)
            await self.bus.publish_inbound(InboundMessage(channel=self.name, sender_id=sender_id, chat_id=reply_to, content=content, media=media_paths, metadata={"message_id": message.message_id}, stream_id=stream_id if use_streaming else None))
            if use_streaming and streaming_session:
                await self._wait_and_close_stream(streaming_session, stream_id)
        except Exception:
            pass

    async def _wait_and_close_stream(self, session: "FeishuStreamingSession", stream_id: str) -> None:
        await self.bus.wait_stream_done(stream_id, timeout=300)
        if not session.closed:
            await self._loop.run_in_executor(None, session.close_sync, session.pending_text or session.current_text)
