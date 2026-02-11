FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Install Node.js 20 for the WhatsApp bridge
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates gnupg git && \
    mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" > /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get purge -y gnupg && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

# Create a non-root user for security
RUN useradd -m -u 1000 nanobot
WORKDIR /home/nanobot/app

# Install Python dependencies first (cached layer)
COPY --chown=nanobot:nanobot pyproject.toml README.md LICENSE ./
RUN mkdir -p nanobot bridge && touch nanobot/__init__.py && \
    uv pip install --system --no-cache . && \
    rm -rf nanobot bridge

# Build the WhatsApp bridge (Node.js part)
# We do this before copying the main Python source to keep it cached
COPY --chown=nanobot:nanobot bridge/package*.json ./bridge/
WORKDIR /home/nanobot/app/bridge
RUN npm install
COPY --chown=nanobot:nanobot bridge/ ./
RUN npm run build
WORKDIR /home/nanobot/app

# Copy the full Python source and install
# This is the layer that will change most frequently
COPY --chown=nanobot:nanobot nanobot/ nanobot/
RUN uv pip install --system --no-cache .

# Create config directory and set permissions
RUN mkdir -p /home/nanobot/.nanobot && chown -R nanobot:nanobot /home/nanobot/.nanobot

# Switch to the non-root user
USER nanobot

# Gateway default port
EXPOSE 18790

ENTRYPOINT ["nanobot"]
CMD ["gateway"]
