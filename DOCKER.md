# nanobot in Docker

nanobot is designed to run efficiently inside Docker.

## Quick Start

```bash
docker build -t nanobot .
./run-docker.sh
```

## Structure

The Docker image is built from the project root. Configuration and workspace are typically mounted from the host to ensure persistence.

## Development

When making changes, rebuild the image:
```bash
docker build -t nanobot .
```
