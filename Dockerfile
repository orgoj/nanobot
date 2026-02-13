# Multi-stage build for nanobot

# =============================================================================
# Stage 1: Python Builder
# =============================================================================
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS python-builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential gcc git ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Copy source code
COPY pyproject.toml README.md LICENSE ./
COPY nanobot/ nanobot/
RUN mkdir -p bridge && touch bridge/.gitkeep

# Build wheel using uv
RUN uv pip install --system --no-cache build && \
    python -m build --wheel && \
    mkdir -p /wheels && \
    cp dist/*.whl /wheels/

# =============================================================================
# Stage 2: WhatsApp Bridge Builder
# =============================================================================
FROM node:20-slim AS bridge-builder

WORKDIR /build

# Install git and ca-certificates
RUN apt-get update && \
    apt-get install -y --no-install-recommends git ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Configure git to use https instead of ssh for GitHub
RUN git config --global url."https://github.com/".insteadOf ssh://git@github.com/

# Copy bridge files
COPY bridge/package.json bridge/tsconfig.json ./
COPY bridge/src/ src/

# Install dependencies and build
RUN npm install && npm run build

# =============================================================================
# Stage 3: Runtime
# =============================================================================
FROM python:3.12-slim-bookworm AS runtime

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install runtime dependencies (minimal + orgoj additions)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl ca-certificates gnupg git gh tmux \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# For chrome run in docker (required for some tools/skills)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libasound2 libpango-1.0-0 libcairo2 \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user for security
RUN useradd -m -u 1000 nanobot
WORKDIR /home/nanobot/app

# Copy and install Python wheel with all dependencies
COPY --from=python-builder /wheels/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && \
    rm /tmp/*.whl && \
    rm -rf /root/.cache/pip

# Copy WhatsApp bridge runtime files
COPY --from=bridge-builder /build/dist ./bridge/dist
COPY --from=bridge-builder /build/node_modules ./bridge/node_modules
COPY --from=bridge-builder /build/package.json ./bridge/

# Create config directory and set permissions
RUN mkdir -p /home/nanobot/.nanobot && chown -R nanobot:nanobot /home/nanobot/.nanobot

# Switch to the non-root user
USER nanobot

# Gateway port
EXPOSE 18790

ENTRYPOINT ["nanobot"]
CMD ["gateway"]
