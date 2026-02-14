"""Z.AI Web tools using the official MCP Python SDK with Streamable HTTP transport."""

import json
import os
from typing import Any

import httpx
from loguru import logger
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from nanobot.agent.tools.base import Tool

# Real MCP endpoints for GLM Coding Plan
ZAI_SEARCH_URL = "https://api.z.ai/api/mcp/web_search_prime/mcp"
ZAI_READER_URL = "https://api.z.ai/api/mcp/web_reader/mcp"


class ZaiMcpBase:
    """Helper class for ZAI tools using the official MCP SDK with Streamable HTTP."""

    def __init__(self, url: str, api_key: str | None = None):
        self._url = url
        self._api_key = api_key or os.environ.get("Z_AI_API_KEY")

    async def _call_mcp(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if not self._api_key:
            return "Error: Z_AI_API_KEY is not configured."

        # Headers for the underlying HTTP client
        headers = {
            "Authorization": f"Bearer {self._api_key}",
        }

        try:
            # We create our own AsyncClient to provide the necessary Authorization header
            async with httpx.AsyncClient(headers=headers, timeout=60.0) as http_client:
                async with streamable_http_client(url=self._url, http_client=http_client) as (
                    read_stream,
                    write_stream,
                    _,
                ):
                    async with ClientSession(read_stream, write_stream) as session:
                        # Step 1: Initialize session
                        await session.initialize()

                        # Step 2: Call tool
                        result = await session.call_tool(tool_name, arguments)

                        # Step 3: Extract text from response
                        full_text = "".join(
                            [content.text for content in result.content if hasattr(content, "text")]
                        )

                        try:
                            return json.loads(full_text)
                        except (json.JSONDecodeError, TypeError):
                            return full_text
        except Exception as e:
            logger.error(f"MCP HTTP Call to {tool_name} failed: {e}")
            return f"Error: {str(e)}"


class ZaiWebSearchTool(Tool, ZaiMcpBase):
    name = "web_search"
    description = "Search the web using Z.AI Prime."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "count": {"type": "integer", "default": 10},
        },
        "required": ["query"],
    }

    def __init__(self, api_key: str | None = None, **kwargs):
        Tool.__init__(self)
        ZaiMcpBase.__init__(self, url=ZAI_SEARCH_URL, api_key=api_key)

    async def execute(self, query: str, count: int = 10, **kwargs: Any) -> str:
        results = await self._call_mcp("webSearchPrime", {"search_query": query})
        if not isinstance(results, list):
            return str(results)
        lines = [f"Results for: {query}\n"]
        for i, item in enumerate(results[:count], 1):
            title = item.get("title") or "No Title"
            link = item.get("link") or item.get("url") or ""
            content = item.get("content") or item.get("summary") or ""
            lines.append(f"{i}. {title}\n   {link}\n   {content}")
        return "\n".join(lines)


class ZaiWebFetchTool(Tool, ZaiMcpBase):
    name = "web_fetch"
    description = "Fetch URL and extract content using Z.AI Reader."
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch"},
            "extract_mode": {"type": "string", "enum": ["markdown", "text"], "default": "markdown"},
        },
        "required": ["url"],
    }

    def __init__(self, api_key: str | None = None, **kwargs):
        Tool.__init__(self)
        ZaiMcpBase.__init__(self, url=ZAI_READER_URL, api_key=api_key)

    async def execute(self, url: str, extract_mode: str = "markdown", **kwargs: Any) -> str:
        result = await self._call_mcp("webReader", {"url": url, "return_format": extract_mode})
        if isinstance(result, str) and result.startswith("Error:"):
            return json.dumps({"error": result, "url": url})
        return json.dumps(
            {"url": url, "status": 200, "text": str(result), "extractor": "zai-mcp-http"}
        )
