# Docker Image Structure

## Overview

The nanobot Docker image is built on `python3.12-bookworm-slim` with Node.js 20 for WhatsApp bridge support. It uses a non-root user for security.

## Base Image

- **Base**: `ghcr.io/astral-sh/uv:python3.12-bookworm-slim`
- **Package Manager**: `uv` (fast Python package installer)
- **Node.js**: v20.x (for WhatsApp bridge)

## User & Permissions

```bash
User: nanobot
UID: 1000
Home: /home/nanobot
```

The container runs as the `nanobot` user by default (non-root for security).

## Directory Structure Inside Container

```
/home/nanobot/
├── .bash_logout         # Bash logout script
├── .bashrc             # Bash configuration
├── .profile            # Profile script
├── .nanobot/           # Config directory (persisted via volume)
│   ├── config.json     # Main configuration
│   └── ...             # Other config files
├── app/                # Application code (mounted from host)
│   ├── LICENSE
│   ├── README.md
│   ├── pyproject.toml
│   ├── nanobot/        # Core Python code
│   └── bridge/         # WhatsApp bridge (Node.js)
└── workspace/          # Working directory (persisted via volume)
    ├── logs/
    │   └── nanobot.log
    └── ...
```

**Note**: The `app/` directory is owned by `root` because it's mounted from the host. The `nanobot` user has read access.

## Environment Variables

```bash
HOME=/home/nanobot
PATH=/usr/local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
```

## Installed Tools

### System Packages
- `curl` - HTTP client
- `git` - Version control
- `gh` - GitHub CLI
- `tmux` - Terminal multiplexer
- `nodejs` - Node.js runtime (v20.x)
- `npm` - Node package manager

### Global NPM Packages
- `@steipete/summarize` - Text summarization tool

### Python Packages
Installed via `uv` (see `pyproject.toml` for full list):
- LiteLLM (provider abstraction)
- Other dependencies

## Accessing the Container

```bash
# Start a bash session in the running container
docker exec -ti nanobot bash

# Run as nanobot user (default)
docker exec -ti nanobot bash

# Run as root (for system operations)
docker exec -ti -u root nanobot bash
```

## Quick Reference Inside Container

```bash
# Check current directory
pwd
# Output: /home/nanobot/app

# List files in home
ls -lA $HOME

# Config location
ls -l ~/.nanobot/

# Workspace location
ls -l ~/workspace/

# Check Python version
python --version
# Output: Python 3.12.x

# Check Node.js version
node --version
# Output: v20.x.x

# Run nanobot CLI
nanobot --help

# Check status
nanobot status
```

## Volume Mounts

When running via `run-docker.sh`, two directories are mounted:

1. **Config**: `instance/.nanobot` → `/home/nanobot/.nanobot`
   - Persisted configuration
   - Channel credentials
   - API keys

2. **Workspace**: `instance/workspace` → `/home/nanobot/workspace`
   - Logs
   - Session data
   - User files

## Ports

- **18790**: Gateway port (exposed by default)

## Entry Point

```dockerfile
ENTRYPOINT ["nanobot"]
CMD ["gateway"]
```

Default command starts the gateway server. Override with:

```bash
# Interactive agent mode
docker exec -ti nanobot nanobot agent

# Check status
docker exec -ti nanobot nanobot status

# Run custom command
docker run --rm nanobot agent -m "Hello"
```

## Common Operations

### Debugging Inside Container

```bash
# Enter container
docker exec -ti nanobot bash

# View logs
tail -f ~/workspace/logs/nanobot.log

# Check config
cat ~/.nanobot/config.json

# Test Python imports
python -c "from nanobot.agent import Agent; print('OK')"

# Check bridge status
cd ~/app/bridge && npm run status
```

### System Maintenance (as root)

```bash
# Enter as root
docker exec -ti -u root nanobot bash

# Install additional packages
apt-get update && apt-get install -y <package>

# Check disk usage
du -sh /home/nanobot/*
```

## Image Layers (Build Cache)

The Dockerfile is optimized for caching:

1. **Base layer**: Python 3.12 + Node.js 20
2. **Dependencies**: `pyproject.toml` (cached if deps don't change)
3. **Bridge**: `bridge/` npm packages (cached if package.json doesn't change)
4. **Source code**: `nanobot/` (rebuilds most frequently)

This ensures fast rebuilds during development.

## Security Notes

- Container runs as non-root user (`nanobot`)
- No `sudo` installed (intentional)
- System packages are minimal (reduces attack surface)
- Config and workspace are isolated from host system
