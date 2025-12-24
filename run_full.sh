#!/bin/bash
set -e

echo "Running SECCAMP in full batch mode..."
docker compose run --rm seccamp --mode full
