# SECCAMP Test Suite

Comprehensive test suite for the SECCAMP real estate scraping and analysis system.

## Test Structure

```
tests/
├── conftest.py              # Pytest configuration and shared fixtures
├── test_url_normalizer.py   # URL normalization tests
├── test_rate_limiter.py     # Rate limiting tests
├── test_cache_manager.py    # Cache management tests
├── test_site_config.py      # Site configuration tests
├── test_database.py         # Database operations tests
└── test_scrapers.py         # Web scraper tests
```

## Test Categories

### Unit Tests (`@pytest.mark.unit`)
Fast, isolated tests that don't require external dependencies:
- URL normalization logic
- Rate limiting calculations
- Cache data structures
- Configuration loading
- Database model validation

### Integration Tests (`@pytest.mark.integration`)
Tests that verify component interactions:
- Database operations with real database
- Cache manager with PostgreSQL
- Rate limiter with database tracking
- Full scraper workflows

### Database Tests (`@pytest.mark.database`)
Tests requiring database access:
- CRUD operations
- ORM model relationships
- Transactions and rollbacks
- Schema migrations

### Scraper Tests (`@pytest.mark.scraper`)
Tests for web scraping functionality:
- BaseScraper abstract class
- Site-specific scrapers
- Cache integration
- Rate limiting integration

### Slow Tests (`@pytest.mark.slow`)
Tests that take significant time:
- Real browser automation
- Performance benchmarks
- Large dataset operations

## Running Tests

### Quick Start

```bash
# Install test dependencies
pip install -r requirements.txt

# Run all tests
./run_test.sh

# Run with coverage report
./run_test.sh --cov
```

### Run Specific Test Types

```bash
# Unit tests only
./run_test.sh unit

# Integration tests only
./run_test.sh integration

# Database tests only
./run_test.sh database

# Scraper tests only
./run_test.sh scraper
```

### Run Specific Tests

```bash
# Run tests matching a pattern
./run_test.sh -k "test_normalize"

# Run a specific test file
pytest tests/test_url_normalizer.py -v

# Run a specific test class
pytest tests/test_database.py::TestDatabaseManager -v

# Run a specific test method
pytest tests/test_database.py::TestDatabaseManager::test_upsert_property_new -v
```

### Advanced Options

```bash
# Verbose output
pytest -v

# Stop on first failure
pytest -x

# Run with Python debugger on failure
pytest --pdb

# Show local variables on failure
pytest -l

# Run tests in parallel (requires pytest-xdist)
pytest -n auto

# Run last failed tests
pytest --lf

# Run tests with detailed output
pytest -vv -s
```

## Test Fixtures

### Shared Fixtures (conftest.py)

#### Database Fixtures
- `temp_db_path` - Temporary database file
- `initialized_db` - Database with schema initialized
- `db_session` - SQLAlchemy session
- `db_manager` - DatabaseManager instance

#### Data Fixtures
- `sample_property_data` - Sample property dictionary
- `sample_ai_score_data` - Sample AI score dictionary
- `sample_html_content` - Sample HTML for parsing

#### Mock Fixtures
- `mock_db_connection` - Mock database connection
- `mock_driver` - Mock Selenium WebDriver
- `mock_response` - Mock HTTP response

### Using Fixtures in Tests

```python
def test_example(db_session, sample_property_data):
    """Test using fixtures."""
    # Use the db_session fixture
    # Use the sample_property_data fixture
    pass
```

## Test Markers

Tests are marked for easy filtering:

```python
@pytest.mark.unit
class TestMyComponent:
    def test_something(self):
        pass

@pytest.mark.integration
@pytest.mark.database
def test_database_integration():
    pass
```

## Coverage Reports

Generate coverage reports:

```bash
# Terminal report
pytest --cov=app --cov-report=term-missing

# HTML report
pytest --cov=app --cov-report=html

# XML report (for CI)
pytest --cov=app --cov-report=xml
```

View HTML coverage report:
```bash
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

## Writing Tests

### Test Structure

```python
import pytest
from module import ClassToTest

@pytest.mark.unit
class TestClassName:
    """Test suite for ClassName."""

    def test_method_does_something(self):
        """Test that method does something."""
        # Arrange
        obj = ClassToTest()
        expected = "result"

        # Act
        result = obj.method()

        # Assert
        assert result == expected

    @pytest.mark.parametrize("input,expected", [
        ("input1", "output1"),
        ("input2", "output2"),
    ])
    def test_parameterized(self, input, expected):
        """Test with multiple inputs."""
        result = function_to_test(input)
        assert result == expected
```

### Best Practices

1. **Arrange, Act, Assert** - Structure tests clearly
2. **One assertion per test** - Tests should do one thing
3. **Descriptive names** - Test names should describe what they test
4. **Use fixtures** - Avoid repetitive setup code
5. **Mock external dependencies** - Tests should be isolated
6. **Test edge cases** - Empty inputs, None values, boundary conditions
7. **Test error conditions** - Exception handling, validation

## CI/CD Integration

### GitHub Actions

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt
      - run: pytest --cov=app --cov-report=xml
      - uses: codecov/codecov-action@v3
```

### Docker

```bash
# Run tests in Docker
docker compose run --rm seccamp pytest
```

## Troubleshooting

### Common Issues

**ImportError: No module named 'app'**
```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
pytest
```

**Database locked errors**
```bash
# Close any existing connections
# Use separate databases for tests
pytest --mock-db
```

**Selenium/WebDriver not found**
```bash
# Skip scraper tests in CI
pytest -m "not scraper"
```

### Debugging Failed Tests

```bash
# Run with Python debugger
pytest --pdb

# Show print statements
pytest -s

# Run last failed tests
pytest --lf

# Run tests with detailed output
pytest -vv -l
```

## Test Coverage Goals

Current coverage targets:

| Module | Target | Current |
|--------|--------|---------|
| URL Normalizer | 100% | ~95% |
| Rate Limiter | 90% | ~85% |
| Cache Manager | 90% | ~85% |
| Site Config | 100% | ~95% |
| Database | 85% | ~80% |
| Scrapers | 70% | ~60% |

## Contributing Tests

When adding new features:

1. Write tests first (TDD)
2. Ensure all tests pass
3. Add fixtures to conftest.py if reusable
4. Update this README if adding new test categories
5. Run coverage report to check coverage

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Pytest Mock Documentation](https://pytest-mock.readthedocs.io/)
- [SQLAlchemy Testing](https://docs.sqlalchemy.org/en/20/orm/testing.html)
- [Selenium Testing Best Practices](https://www.selenium.dev/documentation/test_practices/)
