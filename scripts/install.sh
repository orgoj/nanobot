#!/bin/bash
# Nanobot Local Installation Script (Interactive)
# Run this on the target machine (Ubuntu/Armbian)

set -e

# Colors for better output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

echo -e "${GREEN}🤖 Nanobot Local Installer${NC}"
echo "---------------------------"

# 1. System Dependencies
echo -e "\n${GREEN}[1/5] Installing system dependencies...${NC}"
SUDO=""
if [ "$(id -u)" -ne 0 ]; then
    SUDO="sudo"
fi

$SUDO apt-get update
$SUDO apt-get install -y --no-install-recommends \
    curl ca-certificates gnupg git tmux gh \
    libglib2.0-0 libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 libasound2 libpango-1.0-0 libcairo2

# Install Node.js 20 if missing
if ! command -v node &> /dev/null || ! node -v | grep -q "v20"; then
    echo "🟢 Installing Node.js 20..."
    $SUDO mkdir -p /etc/apt/keyrings
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | $SUDO gpg --dearmor --yes -o /etc/apt/keyrings/nodesource.gpg
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | $SUDO tee /etc/apt/sources.list.d/nodesource.list
    $SUDO apt-get update
    $SUDO apt-get install -y nodejs
fi

# Install uv if missing
if ! command -v uv &> /dev/null; then
    echo "🟢 Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# 2. SSH Keys
echo -e "\n${GREEN}[2/5] Checking SSH keys...${NC}"
if [ ! -f "$HOME/.ssh/id_ed25519" ]; then
    echo "SSH key not found. Generating one..."
    ssh-keygen -t ed25519 -N "" -f "$HOME/.ssh/id_ed25519"
    echo -e "${GREEN}New SSH public key:${NC}"
    cat "$HOME/.ssh/id_ed25519.pub"
    echo "Please add this key to your GitHub account/repo."
else
    echo "SSH key already exists."
fi

# 3. Application Install
echo -e "\n${GREEN}[3/5] Installing Nanobot application...${NC}"
uv pip install --system .

if [ -d "bridge" ]; then
    echo "Building WhatsApp bridge..."
    cd bridge
    npm install
    npm run build
    cd ..
fi

# 4. Systemd Service
echo -e "\n${GREEN}[4/5] Systemd Service Setup${NC}"
read -p "Do you want to create a systemd service for Nanobot? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    SERVICE_PATH="/etc/systemd/system/nanobot.service"
    APP_DIR=$(pwd)
    USER_NAME=$(whoami)
    
    echo "Setting up service..."
    
    # Console logging question
    CONSOLE_LOG=""
    read -p "Mirror logs to physical console (/dev/tty1)? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        CONSOLE_LOG="StandardOutput=journal+console\nStandardError=journal+console\nTTYPath=/dev/tty1"
    fi

    cat << EOF | $SUDO tee $SERVICE_PATH > /dev/null
[Unit]
Description=Nanobot AI Assistant
After=network.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$APP_DIR
Environment=PATH=$HOME/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart=$(command -v python3) -m nanobot.cli.commands gateway
Restart=always
RestartSec=10
$CONSOLE_LOG

[Install]
WantedBy=multi-user.target
EOF

    $SUDO systemctl daemon-reload
    $SUDO systemctl enable nanobot.service
    
    # Allow service restart without password
    echo "Allowing service restart without sudo password..."
    echo "$USER_NAME ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart nanobot.service" | $SUDO tee /etc/sudoers.d/nanobot-service > /dev/null
    $SUDO chmod 440 /etc/sudoers.d/nanobot-service

    echo -e "${GREEN}Service 'nanobot' created and enabled.${NC}"
fi

# 5. Finalize
echo -e "\n${GREEN}[5/5] Installation complete!${NC}"
echo "---------------------------"
echo "To start the bot: systemctl start nanobot (if service created)"
echo "To see logs: journalctl -u nanobot -f"
echo ""
echo "Don't forget to migrate your data (.nanobot and workspace) from your dev machine."
