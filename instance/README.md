# Instance Directory

This directory contains symlinks to the Docker container's config and workspace.

## Setup

### 1. Create symlinks

```bash
# Remove existing symlinks if any
rm -rf instance/.nanobot instance/workspace

# Create symlinks to your locations
ln -s /path/to/your/.nanobot instance/.nanobot
ln -s /path/to/your/workspace instance/workspace
```

### 2. Create config (optional)

```bash
cp instance/config.sh.example instance/config.sh
# Edit instance/config.sh with your settings
```

Available settings:
- `CONTAINER_NAME` - Docker container name (default: "nanobot")
- `TIMEZONE` - Container timezone, e.g. "Europe/Prague" (default: none)
- `INSTANCE_DIR` - Instance directory path (default: "./instance")

## How it works

- `run-docker.sh` sources `instance/config.sh` if it exists
- Symlinks are resolved to absolute paths via `readlink -f`
- Docker mounts the resolved paths
- Each developer has their own local config (gitignored)
