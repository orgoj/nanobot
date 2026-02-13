#!/bin/bash
set -euo pipefail

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Configuration
REMOTE="${1:-nanobotnb}"
# Store data in instance/<REMOTE_NAME>
LOCAL_DIR="${SCRIPT_DIR}/${REMOTE}"

# Help
if [[ "${1:-}" =~ ^(-h|--help)$ ]]; then
    echo "Usage: $0 [REMOTE_HOST]"
    echo "Syncs configuration and workspace from the remote host."
    echo "Data will be saved to: ${SCRIPT_DIR}/<REMOTE_HOST>"
    exit 0
fi

echo "🚀 Fetching data from remote: $REMOTE"
echo "📂 Target directory: $LOCAL_DIR"

# Create directories
mkdir -p "$LOCAL_DIR/.nanobot"
mkdir -p "$LOCAL_DIR/workspace"

# Sync options: Archive, Verbose, Compress, Exclude temporary files
OPTS="-avz --exclude='__pycache__' --exclude='*.pyc' --exclude='.DS_Store' --exclude='.venv' --exclude='node_modeules'"

echo "⬇️  Syncing .nanobot..."
rsync $OPTS "$REMOTE:.nanobot/" "$LOCAL_DIR/.nanobot/"

echo "⬇️  Syncing workspace..."
rsync $OPTS "$REMOTE:workspace/" "$LOCAL_DIR/workspace/"

echo "✅ Done! Data saved to $LOCAL_DIR"
