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
# 'uv sync' creates a local .venv and installs all dependencies automatically
$HOME/.local/bin/uv sync

if [ -d "bridge" ]; then
    echo "Building WhatsApp bridge..."
    cd bridge
    npm install
    npm run build
    cd ..
fi

# 4. User Systemd Service Setup
echo -e "\n${GREEN}[4/5] User Systemd Service Setup${NC}"
read -p "Do you want to create/update a USER systemd service for Nanobot? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    USER_SERVICE_DIR="$HOME/.config/systemd/user"
    SERVICE_PATH="$USER_SERVICE_DIR/nanobot.service"
    APP_DIR=$(pwd)
    
    mkdir -p "$USER_SERVICE_DIR"

    echo "Creating user service file at $SERVICE_PATH..."
    cat << EOF > "$SERVICE_PATH"
[Unit]
Description=Nanobot AI Assistant
After=network.target

[Service]
Type=simple
WorkingDirectory=$APP_DIR
Environment=PATH=$HOME/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
# Use uv run to ensure the app runs in the correct environment
ExecStart=$HOME/.local/bin/uv run nanobot gateway
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF

    # Ensure XDG_RUNTIME_DIR is set for the session to talk to systemd user bus
    export XDG_RUNTIME_DIR="/run/user/$(id -u)"
    
    systemctl --user daemon-reload
    systemctl --user enable nanobot.service
    systemctl --user restart nanobot.service
    
    # Enable lingering (requires sudo once)
    echo "Enabling lingering for $(whoami) to keep service running after logout..."
    sudo loginctl enable-linger $(whoami)

    echo -e "${GREEN}User service 'nanobot' configured and enabled.${NC}"
    echo "Control with: systemctl --user [start|stop|restart|status] nanobot"
fi

# 4.5 Create a wrapper script in ~/.local/bin
if [ ! -f "$HOME/.local/bin/nanobot" ]; then
    echo -e "\n${GREEN}[4.5/5] Creating 'nanobot' command wrapper...${NC}"
    cat << EOF > $HOME/.local/bin/nanobot
#!/bin/bash
# Wrapper to run nanobot from anywhere using uv run
(cd $APP_DIR && $HOME/.local/bin/uv run nanobot "\$@")
EOF
    chmod +x $HOME/.local/bin/nanobot
    echo "Convenience wrapper created at ~/.local/bin/nanobot"
fi

# 5. Finalize
echo -e "\n${GREEN}[5/5] Installation complete!${NC}"
echo "---------------------------"
echo "To start the bot: systemctl --user start nanobot"
echo "To see logs: journalctl --user -u nanobot -f"
echo ""
echo "Try running manually first to verify: uv run nanobot gateway"
