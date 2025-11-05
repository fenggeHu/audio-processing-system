# Integration Tests

This directory contains integration tests for the Production Audio System.

## Test Categories

- `test_end_to_end_flow.py` - Complete audio pipeline testing
- `test_multi_device_concurrent.py` - Multi-device concurrent processing
- `test_stability.py` - Long-term stability and stress testing  
- `test_platform_compatibility.py` - Cross-platform compatibility

## Running Integration Tests

```bash
# Run all integration tests
pytest tests/integration/ -v

# Run specific test category
pytest tests/integration/test_end_to_end_flow.py -v

# Run with markers
pytest -m integration -v
pytest -m slow -v
```

## Test Markers

- `@pytest.mark.integration` - Integration test
- `@pytest.mark.slow` - Long-running test
- `@pytest.mark.performance` - Performance test

