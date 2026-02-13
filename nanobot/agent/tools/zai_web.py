"""Z.AI Web tools: web_search and web_fetch using ZAI MCP."""

import json
import os
import uuid
from typing import Any
from urllib.parse import urljoin

import httpx

from nanobot.agent.tools.base import Tool

# Default Endpoints (can be overridden by config)
ZAI_SEARCH_ENDPOINT = "https://api.z.ai/api/mcp/web_search_prime/mcp"
ZAI_READER_ENDPOINT = "https://api.z.ai/api/mcp/web_reader/mcp"


class ZaiClient:
    """Minimal MCP HTTP Client for Z.AI."""

    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
        }

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Call a tool via MCP over HTTP (SSE + POST)."""
        request_id = str(uuid.uuid4())

        async with httpx.AsyncClient(timeout=60.0) as client:
            # Connect to SSE endpoint
            async with client.stream("GET", self.base_url, headers=self.headers) as response:
                response.raise_for_status()

                event_type = None
                post_endpoint = None

                # Simple SSE parser
                async for line in response.aiter_lines():
                    if not line.strip():
                        event_type = None
                        continue

                    if line.startswith("event:"):
                        event_type = line.split(":", 1)[1].strip()
                    elif line.startswith("data:"):
                        data = line.split(":", 1)[1].strip()

                        if event_type == "endpoint":
                            post_endpoint = data
                            if not post_endpoint.startswith("http"):
                                post_endpoint = urljoin(str(response.url), post_endpoint)

                            # Send the tool call
                            payload = {
                                "jsonrpc": "2.0",
                                "id": request_id,
                                "method": "tools/call",
                                "params": {"name": tool_name, "arguments": arguments},
                            }

                            # Use a separate call for POST
                            await client.post(
                                post_endpoint,
                                json=payload,
                                headers={
                                    "Content-Type": "application/json",
                                    "Authorization": f"Bearer {self.api_key}",
                                },
                            )

                        elif event_type == "message":
                            try:
                                msg = json.loads(data)
                                if msg.get("id") == request_id:
                                    if "error" in msg:
                                        raise Exception(f"RPC Error: {msg['error']}")

                                    # MCP tool call result structure
                                    result = msg.get("result", {})
                                    if result.get("isError"):
                                        raise Exception(f"Tool execution error: {result}")

                                    # Extract content
                                    content_items = result.get("content", [])
                                    text_content = []
                                    for item in content_items:
                                        if item.get("type") == "text":
                                            text_content.append(item.get("text", ""))

                                    full_text = "\n".join(text_content)

                                    # Try to parse as JSON if it looks like it
                                    try:
                                        return json.loads(full_text)
                                    except json.JSONDecodeError:
                                        return full_text
                            except json.JSONDecodeError:
                                pass


class ZaiWebSearchTool(Tool):
    """Search the web using Z.AI WebSearchPrime."""

    name = "web_search"
    description = "Search the web using Z.AI. Returns titles, URLs, and snippets."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "count": {
                "type": "integer",
                "description": "Results (1-10)",
                "minimum": 1,
                "maximum": 10,
            },
        },
        "required": ["query"],
    }

    def __init__(
        self, api_key: str | None = None, base_url: str | None = None, max_results: int = 5
    ):
        self.api_key = api_key or os.environ.get("Z_AI_API_KEY") or os.environ.get("ZAI_API_KEY")
        self.base_url = base_url or ZAI_SEARCH_ENDPOINT
        self.max_results = max_results

    async def execute(self, query: str, count: int | None = None, **kwargs: Any) -> str:
        if not self.api_key:
            return "Error: Z_AI_API_KEY not configured"

        client = ZaiClient(self.api_key, self.base_url)
        try:
            # Map parameters to webSearchPrime
            n = min(max(count or self.max_results, 1), 10)
            args = {
                "search_query": query,
            }

            results = await client.call_tool("webSearchPrime", args)

            # results should be a list of objects
            if isinstance(results, str):
                return results  # Error or raw string

            if not isinstance(results, list):
                # Maybe it's wrapped?
                return str(results)

            lines = [f"Results for: {query}\n"]
            for i, item in enumerate(results[:n], 1):
                # Normalize keys
                title = item.get("title", "")
                url = item.get("link", "")
                content = item.get("content", "") or item.get("summary", "")

                lines.append(f"{i}. {title}\n   {url}")
                if content:
                    lines.append(f"   {content}")
            return "\n".join(lines)

        except Exception as e:
            return f"Error executing Z.AI search: {e}"


class ZaiWebFetchTool(Tool):
    """Fetch and extract content using Z.AI Web Reader."""

    name = "web_fetch"
    description = "Fetch URL and extract readable content (HTML → markdown/text)."
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch"},
            "extract_mode": {
                "type": "string",
                "enum": ["markdown", "text"],
                "default": "markdown",
            },
            "max_chars": {"type": "integer", "minimum": 100},
        },
        "required": ["url"],
    }

    def __init__(
        self, api_key: str | None = None, base_url: str | None = None, max_chars: int = 50000
    ):
        self.api_key = api_key or os.environ.get("Z_AI_API_KEY") or os.environ.get("ZAI_API_KEY")
        self.base_url = base_url or ZAI_READER_ENDPOINT
        self.max_chars = max_chars

    async def execute(
        self,
        url: str,
        extract_mode: str = "markdown",
        max_chars: int | None = None,
        **kwargs: Any,
    ) -> str:
        if not self.api_key:
            return json.dumps({"error": "Z_AI_API_KEY not configured", "url": url})

        client = ZaiClient(self.api_key, self.base_url)
        max_chars = max_chars or self.max_chars

        try:
            args = {"url": url, "return_format": extract_mode, "no_cache": True}

            # Tool name: 'webReader'
            result = await client.call_tool("webReader", args)

            text = str(result)
            truncated = len(text) > max_chars
            if truncated:
                text = text[:max_chars]

            # Try to match the output format of original WebFetchTool
            return json.dumps(
                {
                    "url": url,
                    "finalUrl": url,  # We don't know the final URL from ZAI reader easily
                    "status": 200,
                    "extractor": "zai-reader",
                    "truncated": truncated,
                    "length": len(text),
                    "text": text,
                }
            )

        except Exception as e:
            return json.dumps({"error": f"Error executing Z.AI fetch: {e}", "url": url})
