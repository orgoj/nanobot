#!/bin/bash
# Nanobot Local Installation Script (Interactive) - Revised for User installation
# Run this on the target machine as the user who will run the bot (e.g. nanobot)

set -e

# Colors for better output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${GREEN}🤖 Nanobot Local Installer (User Mode)${NC}"
echo "---------------------------"

# 0. Check for sudo availability
if ! command -v sudo &> /dev/null; then
    echo -e "${RED}Error: sudo is required for system packages.${NC}"
    exit 1
fi

# Fix potential permission issues if root ran something here before
echo "Checking directory permissions..."
sudo chown -R $(whoami):$(whoami) $HOME

# 1. System Dependencies (Requires sudo password)
echo -e "\n${GREEN}[1/5] Installing system dependencies...${NC}"
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
    curl ca-certificates gnupg git tmux gh \
    libglib2.0-0 libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 libasound2 libpango-1.0-0 libcairo2

# Install Node.js 20 if missing
if ! command -v node &> /dev/null || ! node -v | grep -q "v20"; then
    echo "🟢 Installing Node.js 20..."
    sudo mkdir -p /etc/apt/keyrings
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | sudo gpg --dearmor --yes -o /etc/apt/keyrings/nodesource.gpg
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | sudo tee /etc/apt/sources.list.d/nodesource.list
    sudo apt-get update
    sudo apt-get install -y nodejs
fi

# Install uv for current user
if [ ! -f "$HOME/.local/bin/uv" ]; then
    echo "🟢 Installing uv for $(whoami)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Ensure it's in PATH for this session
    export PATH="$HOME/.local/bin:$PATH"
    # Add to bashrc if not already there
    if ! grep -q ".local/bin" "$HOME/.bashrc"; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
    fi
else
    echo "uv is already installed in $HOME/.local/bin"
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
# Use uv to sync dependencies
$HOME/.local/bin/uv pip install .

if [ -d "bridge" ]; then
    echo "Building WhatsApp bridge..."
    cd bridge
    npm install
    npm run build
    cd ..
fi

# 4. Systemd Service Setup
echo -e "\n${GREEN}[4/5] Systemd Service Setup${NC}"
read -p "Do you want to create/update a systemd service for Nanobot? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    SERVICE_PATH="/etc/systemd/system/nanobot.service"
    APP_DIR=$(pwd)
    USER_NAME=$(whoami)
    
    # Console logging question
    CONSOLE_LOG=""
    read -p "Mirror logs to physical console (/dev/tty1)? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        CONSOLE_LOG="StandardOutput=journal+console\nStandardError=journal+console\nTTYPath=/dev/tty1"
    else
        CONSOLE_LOG="StandardOutput=journal\nStandardError=journal"
    fi

    echo "Creating service file at $SERVICE_PATH..."
    sudo tee $SERVICE_PATH > /dev/null << EOF
[Unit]
Description=Nanobot AI Assistant
After=network.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$APP_DIR
# Explicitly set PATH to include user's uv installation
Environment=PATH=$HOME/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
# Use uv run to ensure the app runs in the correct environment
ExecStart=$HOME/.local/bin/uv run nanobot gateway
Restart=always
RestartSec=10
$CONSOLE_LOG

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable nanobot.service
    
    # Allow service restart without password
    echo "Configuring sudoers for nanobot restart..."
    echo "$USER_NAME ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart nanobot.service" | sudo tee /etc/sudoers.d/nanobot-service > /dev/null
    sudo chmod 440 /etc/sudoers.d/nanobot-service

    echo -e "${GREEN}Service 'nanobot' configured.${NC}"
fi

# 5. Finalize
echo -e "\n${GREEN}[5/5] Installation complete!${NC}"
echo "---------------------------"
echo "To restart the bot: sudo systemctl restart nanobot"
echo "To see logs: journalctl -u nanobot -f"
echo ""
echo "Try running manually first to verify: uv run nanobot gateway"
