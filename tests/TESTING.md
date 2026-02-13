# Testing Guide

This guide explains how to run the nanobot router tests.

## Prerequisites

The tests require `pytest` and `pytest-asyncio`:

```bash
# Install with pip
pip install pytest pytest-asyncio

# Or install nanobot with dev dependencies
pip install -e ".[dev]"

# Or with uv
uv pip install pytest pytest-asyncio
```

## Running Tests

### Option 1: Run All Router Tests

```bash
cd /projects/nanobot-turbo
python -m pytest tests/router/ -v
```

### Option 2: Run Specific Test File

```bash
# Test models
python -m pytest tests/router/test_models.py -v

# Test classifier
python -m pytest tests/router/test_classifier.py -v

# Test sticky routing
python -m pytest tests/router/test_sticky.py -v

# Test calibration
python -m pytest tests/router/test_calibration.py -v

# Test integration
python -m pytest tests/router/test_integration.py -v
```

### Option 3: Run Specific Test

```bash
# Run a specific test class
python -m pytest tests/router/test_models.py::TestRoutingTier -v

# Run a specific test method
python -m pytest tests/router/test_classifier.py::TestClientSideClassifier::test_classify_simple_query -v
```

### Option 4: Run with Coverage

```bash
# Install coverage tool
pip install pytest-cov

# Run with coverage report
python -m pytest tests/router/ --cov=nanobot.agent.router --cov-report=html

# View coverage report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

### Option 5: Run with Verbose Output

```bash
python -m pytest tests/router/ -v -s
```

### Option 6: Stop on First Failure

```bash
python -m pytest tests/router/ -x
```

## Test Structure

```
tests/router/
├── __init__.py              # Package marker
├── README.md                # Testing documentation
├── test_models.py           # Data model tests
├── test_classifier.py       # Client-side classifier tests
├── test_sticky.py          # Sticky routing tests
├── test_calibration.py     # Auto-calibration tests
└── test_integration.py     # Integration tests
```

## Manual Testing

If pytest is not available, you can test manually:

```python
# Test basic classification
from nanobot.agent.router import classify_content

decision, scores = classify_content("Write a Python function to sort a list")
print(f"Tier: {decision.tier.value}")
print(f"Confidence: {decision.confidence}")
print(f"Layer: {decision.layer}")

# View all dimension scores
for dim, score in scores.to_dict().items():
    print(f"{dim}: {score:.2f}")
```

## Continuous Integration

For CI/CD pipelines:

```bash
# Install dependencies
pip install -e ".[dev]"

# Run tests
python -m pytest tests/router/ -v --tb=short

# Or with coverage
python -m pytest tests/router/ --cov=nanobot.agent.router --cov-report=xml
```

## Test Markers

The tests use pytest markers:

- No special markers for basic tests
- `@pytest.mark.asyncio` for async tests (handled automatically)

## Troubleshooting

### "No module named pytest"

Install pytest:
```bash
pip install pytest pytest-asyncio
```

### Import errors

Make sure you're in the project root:
```bash
cd /projects/nanobot-turbo
python -m pytest tests/router/
```

### Async test failures

Ensure pytest-asyncio is installed:
```bash
pip install pytest-asyncio
```

The `pyproject.toml` already has configuration for async tests:
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

## Expected Test Output

A successful test run should look like:

```
tests/router/test_models.py::TestRoutingTier::test_tier_values PASSED
tests/router/test_models.py::TestRoutingTier::test_tier_from_string PASSED
tests/router/test_classifier.py::TestClientSideClassifier::test_classify_simple_query PASSED
...

============================== X passed in Y seconds ==============================
```

## Writing New Tests

When adding new features, add corresponding tests:

```python
# tests/router/test_feature.py
import pytest
from nanobot.agent.router import YourFeature

class TestYourFeature:
    """Tests for YourFeature."""
    
    def test_basic_functionality(self):
        """Test basic feature operation."""
        feature = YourFeature()
        result = feature.do_something()
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_async_functionality(self):
        """Test async feature operation."""
        feature = YourFeature()
        result = await feature.do_something_async()
        assert result is not None
```

## Test Coverage Goals

- Models: 100%
- Classifier: 90%+
- Sticky routing: 90%+
- Calibration: 85%+
- Integration: 80%+

Current status can be checked with:
```bash
python -m pytest tests/router/ --cov=nanobot.agent.router --cov-report=term-missing
```
