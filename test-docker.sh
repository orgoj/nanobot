#!/bin/bash
# test-docker.sh - Spustí testy v izolovaném kontejneru pomocí Dockerfile.test

echo "📦 Stavím testovací image..."
# Používáme tar pro přenos souborů, aby Docker viděl i tests/ bez změny .dockerignore
tar -c nanobot tests pyproject.toml README.md LICENSE Dockerfile.test | docker build -t nanobot-test -f Dockerfile.test -

echo "🚀 Spouštím testy..."
docker run --rm nanobot-test "$@"
