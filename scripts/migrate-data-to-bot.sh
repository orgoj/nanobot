#!/bin/bash
# Push data from local dev machine to the bot machine
# Follows the same logic as run-docker.sh to find config and workspace
# Usage: ./scripts/migrate-data-to-bot.sh [user@]host

set -e

TARGET=$1
INSTANCE_DIR="${INSTANCE_DIR:-./instance}"

if [ -z "$TARGET" ]; then
    echo "Usage: $0 [user@]host"
    exit 1
fi

# Load instance config if exists (to match run-docker.sh logic)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

if [ -f "$PROJECT_ROOT/instance/config.sh" ]; then
    source "$PROJECT_ROOT/instance/config.sh"
fi

# Resolve paths (following run-docker.sh pattern with fallbacks)
if [ -d "$INSTANCE_DIR" ]; then
    NANOBOT_CONFIG="$(readlink -f "$INSTANCE_DIR/.nanobot")"
    NANOBOT_WORKSPACE="$(readlink -f "$INSTANCE_DIR/workspace")"
else
    # Standard locations if instance/ doesn't exist
    NANOBOT_CONFIG="$HOME/.nanobot"
    NANOBOT_WORKSPACE="$PROJECT_ROOT/workspace"
fi

echo "🚚 Syncing data to $TARGET..."
echo "   Source Config: $NANOBOT_CONFIG"
echo "   Source Workspace: $NANOBOT_WORKSPACE"

# Sync .nanobot
if [ -d "$NANOBOT_CONFIG" ]; then
    echo "📂 Syncing .nanobot..."
    rsync -avzL --progress "$NANOBOT_CONFIG/" "$TARGET:~/.nanobot/"
fi

# Sync workspace
if [ -d "$NANOBOT_WORKSPACE" ]; then
    echo "📂 Syncing workspace..."
    # Following run-docker.sh pattern: mount to /home/nanobot/workspace
    rsync -avzL --progress "$NANOBOT_WORKSPACE/" "$TARGET:~/workspace/"
fi

echo "✅ Data migrated. Restart the bot on the target machine to apply changes."
