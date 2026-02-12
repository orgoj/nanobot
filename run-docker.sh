#!/bin/bash
# Spuštění nanobot v Docker kontejneru s Telegram a Z.AI podporou

set -e

CONTAINER_NAME="nanobot"
IMAGE_NAME="nanobot"

# Kontrola, zda kontejner už běží
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

# Kontrola konfigurace
if [ ! -f ~/.nanobot/config.json ]; then
    echo "❌ Chybí konfigurační soubor ~/.nanobot/config.json"
    echo "   Vytvořte ho podle config.json.example"
    exit 1
fi

# Vytvoření workspace, pokud neexistuje
mkdir -p ~/work/nanobot/workspace

echo "🚀 Spouštím nanobot kontejner..."
docker run -d \
  --name "$CONTAINER_NAME" \
  -v ~/work/nanobot/.nanobot:/home/nanobot/.nanobot \
  -v ~/work/nanobot/workspace:/home/nanobot/workspace \
  --restart unless-stopped \
  "$IMAGE_NAME"

echo "✅ Kontejner '$CONTAINER_NAME' běží!"
echo ""
echo "📋 Užitečné příkazy:"
echo "   docker logs -f $CONTAINER_NAME     # Sledovat logy"
echo "   docker stop $CONTAINER_NAME        # Zastavit"
echo "   docker restart $CONTAINER_NAME     # Restartovat"
echo "   docker exec -it $CONTAINER_NAME sh # Připojit se dovnitř"
