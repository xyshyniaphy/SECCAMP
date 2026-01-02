#!/bin/bash

# Test runner script for SECCAMP
# Usage: ./run_test.sh [test_type] [options]
#
# Examples:
#   ./run_test.sh                    # Run all tests
#   ./run_test.sh unit               # Run unit tests only
#   ./run_test.sh integration        # Run integration tests only
#   ./run_test.sh database           # Run database tests only
#   ./run_test.sh --cov             # Run all tests with coverage report
#   ./run_test.sh -v                # Run with verbose output
#   ./run_test.sh -k "test_normalize"  # Run specific tests

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default options
PYTEST_ARGS=""
TEST_TYPE=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        unit|integration|database|scraper|slow)
            TEST_TYPE="$1"
            shift
            ;;
        -v|--verbose)
            PYTEST_ARGS="$PYTEST_ARGS -v"
            shift
            ;;
        --cov|--coverage)
            PYTEST_ARGS="$PYTEST_ARGS --cov=app --cov-report=term-missing --cov-report=html"
            shift
            ;;
        -k|--keyword)
            PYTEST_ARGS="$PYTEST_ARGS -k $2"
            shift 2
            ;;
        -x|--exitfirst)
            PYTEST_ARGS="$PYTEST_ARGS -x"
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [test_type] [options]"
            echo ""
            echo "Test types:"
            echo "  unit            Run unit tests only"
            echo "  integration     Run integration tests only"
            echo "  database        Run database tests only"
            echo "  scraper         Run scraper tests only"
            echo "  slow            Run slow tests only"
            echo ""
            echo "Options:"
            echo "  -v, --verbose   Verbose output"
            echo "  --cov           Generate coverage report"
            echo "  -k PATTERN      Run tests matching pattern"
            echo "  -x, --exitfirst Exit on first failure"
            echo "  -h, --help      Show this help"
            exit 0
            ;;
        *)
            PYTEST_ARGS="$PYTEST_ARGS $1"
            shift
            ;;
    esac
done

# Add marker for specific test types
if [ -n "$TEST_TYPE" ]; then
    PYTEST_ARGS="$PYTEST_ARGS -m $TEST_TYPE"
fi

echo -e "${GREEN}Running SECCAMP tests...${NC}"
echo "pytest_args: $PYTEST_ARGS"
echo ""

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}Error: pytest is not installed${NC}"
    echo "Install with: pip install -r requirements.txt"
    exit 1
fi

# Run pytest
python -m pytest $PYTEST_ARGS tests/

# Exit with pytest's exit code
TEST_STATUS=$?

if [ $TEST_STATUS -eq 0 ]; then
    echo ""
    echo -e "${GREEN}All tests passed! ✓${NC}"

    # Show coverage report if generated
    if [ -f "htmlcov/index.html" ]; then
        echo ""
        echo "Coverage report: file://$(pwd)/htmlcov/index.html"
    fi
else
    echo ""
    echo -e "${RED}Tests failed with exit code $TEST_STATUS${NC}"
fi

exit $TEST_STATUS
