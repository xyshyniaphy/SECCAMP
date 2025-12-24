#!/bin/bash
# Usage: ./run_dev.sh [scrape|full]
# Default mode: full

MODE=${1:-full}

echo "Running SECCAMP in DEV mode ($MODE)..."
echo "Source files are mounted for hot-reload"
echo ""
docker compose -f docker-compose.dev.yml run --rm seccamp --mode "$MODE"
