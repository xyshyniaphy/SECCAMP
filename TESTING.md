# Testing Quick Reference

Quick reference for running tests in the SECCAMP project.

## Installation

```bash
# Install test dependencies
pip install -r requirements.txt
```

## Run Tests

```bash
# All tests
./run_test.sh

# Unit tests only (fast)
./run_test.sh unit

# Integration tests
./run_test.sh integration

# Database tests
./run_test.sh database

# With coverage report
./run_test.sh --cov
```

## pytest Commands

```bash
# Run all tests
pytest

# Verbose output
pytest -v

# Stop on first failure
pytest -x

# Run specific test file
pytest tests/test_url_normalizer.py

# Run specific test class
pytest tests/test_database.py::TestDatabaseManager

# Run specific test method
pytest tests/test_database.py::TestDatabaseManager::test_upsert_property_new

# Run tests matching pattern
pytest -k "test_normalize"

# Run with Python debugger
pytest --pdb
```

## Test Files

| File | Tests | Description |
|------|-------|-------------|
| `test_url_normalizer.py` | 20+ | URL normalization tests |
| `test_rate_limiter.py` | 15+ | Rate limiting tests |
| `test_cache_manager.py` | 20+ | Cache management tests |
| `test_site_config.py` | 25+ | Site configuration tests |
| `test_database.py` | 30+ | Database operations tests |
| `test_scrapers.py` | 20+ | Web scraper tests |

## Test Markers

- `unit` - Fast, isolated tests
- `integration` - Component interaction tests
- `database` - Database-dependent tests
- `scraper` - Web scraping tests
- `slow` - Long-running tests

## Coverage

```bash
# Generate coverage report
pytest --cov=app --cov-report=html

# View report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

## Troubleshooting

**ImportError:**
```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
pytest
```

**Database errors:**
```bash
# Use temporary databases
pytest -m "not database"
```

**Selenium errors:**
```bash
# Skip scraper tests
pytest -m "not scraper"
```

## Documentation

See `tests/README.md` for detailed documentation.
