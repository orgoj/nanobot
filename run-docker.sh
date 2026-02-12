#!/bin/bash
# Spuštění nanobot v Docker kontejneru

set -e

# ========================================
# Configuration (defaults, override in instance/config.sh)
# ========================================
IMAGE_NAME="nanobot"
CONTAINER_NAME="${CONTAINER_NAME:-nanobot}"
INSTANCE_DIR="${INSTANCE_DIR:-./instance}"
TIMEZONE="${TIMEZONE:-}"  # Optional, e.g. "Europe/Prague"

# Load instance config if exists
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/instance/config.sh" ]; then
    source "$SCRIPT_DIR/instance/config.sh"
fi

# ========================================
# Setup
# ========================================
cd "$SCRIPT_DIR"

# Resolve symlinks to absolute paths
NANOBOT_CONFIG="$(readlink -f "$INSTANCE_DIR/.nanobot")"
NANOBOT_WORKSPACE="$(readlink -f "$INSTANCE_DIR/workspace")"

# ========================================
# Checks
# ========================================
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "⚠️  Kontejner '$CONTAINER_NAME' už existuje."
    read -p "Chcete ho zastavit a smazat? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🛑 Zastavuji a mažu starý kontejner..."
        docker stop "$CONTAINER_NAME" 2>/dev/null || true
        docker rm "$CONTAINER_NAME" 2>/dev/null || true
    else
        echo "❌ Ukončuji. Nejdřív smažte starý kontejner ručně:"
        echo "   docker stop $CONTAINER_NAME && docker rm $CONTAINER_NAME"
        exit 1
    fi
fi

mkdir -p "$NANOBOT_CONFIG"
mkdir -p "$NANOBOT_WORKSPACE"

if [ ! -f "$NANOBOT_CONFIG/config.json" ]; then
    echo "❌ Chybí konfigurační soubor $NANOBOT_CONFIG/config.json"
    echo "   Vytvořte ho podle config.json.example"
    exit 1
fi

# ========================================
# Run
# ========================================
echo "🚀 Spouštím nanobot kontejner..."
echo "   Config: $NANOBOT_CONFIG"
echo "   Workspace: $NANOBOT_WORKSPACE"

# Build docker run args
DOCKER_ARGS=(
  --name "$CONTAINER_NAME"
  -v "$NANOBOT_CONFIG:/home/nanobot/.nanobot"
  -v "$NANOBOT_WORKSPACE:/home/nanobot/workspace"
  --restart unless-stopped
)

# Add timezone if specified
if [ -n "$TIMEZONE" ]; then
  DOCKER_ARGS+=(-e "TZ=$TIMEZONE")
  echo "   Timezone: $TIMEZONE"
fi

docker run -d "${DOCKER_ARGS[@]}" "$IMAGE_NAME"

echo "✅ Kontejner '$CONTAINER_NAME' běží!"
echo ""
echo "📋 Užitečné příkazy:"
echo "   docker logs -f $CONTAINER_NAME     # Sledovat logy"
echo "   docker stop $CONTAINER_NAME        # Zastavit"
echo "   docker restart $CONTAINER_NAME     # Restartovat"
echo "   docker exec -it $CONTAINER_NAME sh # Připojit se dovnitř"
