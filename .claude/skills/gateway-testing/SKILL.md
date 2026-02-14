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

## Scripts

### Important: Script Portability
All scripts in this skill MUST use relative paths resolved from skill root:
- ✅ GOOD: `scripts/start.sh` (path from skill directory)
- ❌ BAD: `../scripts/start.sh` (path from parent directory)
- ALWAYS verify paths work from skill directory

### Script Details
- **`scripts/start.sh`**: Spustí nanobota v tmux session `nanobot-gateway`.
- **`scripts/stop.sh`**: Ukončí nanobot gateway session.

## Logy
- Strukturované logy: `~/.nanobot/logs/nanobot.jsonl`
- Výstup konzole: `~/.nanobot/logs/gateway_stdout.log`
