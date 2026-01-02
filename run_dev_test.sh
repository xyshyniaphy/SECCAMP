#!/bin/bash

# Development test runner - runs tests against local code without rebuild
# This is useful for rapid test iteration during development

set -e

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Install/update test dependencies
pip install -q pytest pytest-cov pytest-mock pytest-asyncio pytest-xdist

# Set PYTHONPATH to include app directory
export PYTHONPATH="${PYTHONPATH}:$(pwd)/app"

echo "🧪 Running tests in development mode..."
echo ""

# Run tests with Python's unittest discovery
python -m pytest "$@"

echo ""
echo "✅ Tests completed!"
