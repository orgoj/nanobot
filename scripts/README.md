# Nanobot Installation & Migration

This project is prepared to run directly on a Linux machine (Ubuntu/Armbian) without Docker.

## 1. Initial Installation on the Bot Machine

1.  Clone this repository to the target machine (e.g., your laptop).
2.  Run the installation script:
    ```bash
    bash scripts/install.sh
    ```
3.  The script is interactive and will:
    *   Install required system packages (Node.js, uv, Chrome libraries).
    *   Generate an SSH key (add it to GitHub to enable git pulls).
    *   Offer to create a systemd service.
    *   Offer to mirror logs to the physical console (`/dev/tty1`).

## 2. Data Migration from Development Machine

From your main computer, transfer your existing configuration and workspace:
```bash
./scripts/migrate-data-to-bot.sh nanobot@nanobotnb
```

## 3. Updates

On the bot machine in the project directory:
```bash
git pull
# If dependencies changed:
uv pip install --system .
# If the service changed or just to restart:
sudo systemctl restart nanobot
```
Alternatively, you can run `scripts/install.sh` again; it is idempotent.
