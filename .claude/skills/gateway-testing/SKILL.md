---
name: gateway-testing
description: "Testování nanobot gateway, monitoring logů a analýza tiered modelů v praxi."
---

# Gateway Testing Skill

Tento skill slouží k řízenému testování nanobota v režimu gateway (např. přes Telegram).

## Workflow

1. **Start**: Spusť gateway v tmuxu: `scripts/start.sh`
2. **Monitor**: Sleduj logy v reálném čase: `tail -f ~/.nanobot/logs/nanobot.jsonl | jq .`
3. **Test**: Komunikuj s botem na Telegramu. Zkus spawnout subagenta a poslat mu korekci.
4. **Stop**: Ukonči gateway: `scripts/stop.sh`
5. **Analyze**: Zkontroluj logy na chyby a využití modelů (chat vs task).

## Logy
- Strukturované logy: `~/.nanobot/logs/nanobot.jsonl`
- Výstup konzole: `~/.nanobot/logs/gateway_stdout.log`
