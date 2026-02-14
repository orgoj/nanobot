import asyncio
import json

from nanobot.agent.tools.zai_web import ZaiWebFetchTool, ZaiWebSearchTool
from nanobot.config.loader import load_config
from nanobot.utils.telegram_markdown import markdown_to_telegram


async def test():
    print("--- Testing Config Loading ---")
    config = load_config()
    api_key = config.providers.zhipu.api_key
    if not api_key:
        print("❌ Error: No Zhipu API key found in config!")
        return

    print(f"✅ Config loaded. API Key starts with: {api_key[:5]}...")

    print("\n--- Testing ZAI Web Search ---")
    search_tool = ZaiWebSearchTool(api_key=api_key)
    try:
        results = await search_tool.execute(query="Prague weather", count=1)
        print("✅ Search results received:")
        print(results[:200] + "...")
    except Exception as e:
        print(f"❌ Search failed: {e}")

    print("\n--- Testing ZAI Web Fetch ---")
    fetch_tool = ZaiWebFetchTool(api_key=api_key)
    try:
        fetch_res_raw = await fetch_tool.execute(url="https://example.com")
        fetch_res = json.loads(fetch_res_raw)
        if "text" in fetch_res:
            print(f"✅ Fetch successful. Title: {fetch_res.get('title')}")
            print(f"✅ Content length: {len(fetch_res['text'])}")
        else:
            print(f"❌ Fetch returned error: {fetch_res}")
    except Exception as e:
        print(f"❌ Fetch failed: {e}")

    print("\n--- Testing Telegram HTML Conversion ---")
    test_md = """# Heading
This is **bold**, this is *italic*.
- Item 1
- Item 2

| Table | Col |
|-------|-----|
| Val 1 | Val 2 |

[Google](https://google.com)
`code`
```python
print('hello')
```
"""
    html_output = markdown_to_telegram(test_md)
    print("✅ Conversion to HTML result:")
    print(html_output)

    # Basic assertions
    assert "<b>" in html_output
    assert "<i>" in html_output
    assert "<a href=" in html_output
    assert "<pre>" in html_output
    print("\n✅ All renderer tests passed!")


if __name__ == "__main__":
    asyncio.run(test())
