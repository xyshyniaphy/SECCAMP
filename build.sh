#!/bin/bash
set -e

echo "Building SECCAMP Docker image..."
docker compose build
echo "Build complete!"
