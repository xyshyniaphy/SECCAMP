#!/bin/bash
set -e

echo "Running SECCAMP in scrape mode..."
docker compose run --rm seccamp --mode scrape
