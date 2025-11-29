# Test Suite

This directory contains the unit test suite for the Caddx MQTT Controller.

## Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run with coverage report
pytest --cov=src --cov-report=html --cov-report=term

# Run specific test file
pytest tests/test_partition.py

# Run specific test class
pytest tests/test_partition.py::TestPartitionStateTransitions

# Run specific test
pytest tests/test_partition.py::TestPartitionStateTransitions::test_partition_creation
```

## Test Coverage

The test suite focuses on critical business logic:

- **Protocol utilities** (`test_protocol_utils.py`) - 100% coverage
  - Fletcher-16 checksum calculation
  - PIN encoding to bytearray
  - Bit extraction operations

- **Partition state machine** (`test_partition.py`) - 100% coverage
  - State transitions (DISARMED, ARMED_HOME, ARMED_AWAY, PENDING, TRIGGERED, ARMING)
  - State priority and precedence
  - Registry management
  - Condition flag interpretation

- **Zone management** (`test_zone.py`) - 99% coverage
  - Zone properties (bypassed, faulted, trouble)
  - Partition membership
  - Condition and type masks
  - Registry management

- **Message protocol** (`test_message_protocol.py`)
  - Byte stuffing/unstuffing
  - Message validation
  - Checksum verification

- **MQTT integration** (`test_mqtt.py`)
  - Topic generation
  - Config payload structure
  - State payload formatting
  - Command parsing

## Test Organization

Tests are organized by component:

- `conftest.py` - Pytest configuration and shared fixtures
- `test_protocol_utils.py` - Low-level protocol functions
- `test_message_protocol.py` - Message encoding/decoding
- `test_partition.py` - Partition state management
- `test_zone.py` - Zone state management
- `test_mqtt.py` - MQTT topic and payload generation

## Coverage Report

After running tests with coverage, open `htmlcov/index.html` in a browser to view the detailed coverage report.

## Writing New Tests

When adding new tests:

1. Place tests in the appropriate file based on the component being tested
2. Use descriptive class names starting with `Test`
3. Use descriptive test method names starting with `test_`
4. Clear registries in `setup_method` for partition/zone tests to avoid state pollution
5. Test edge cases and error conditions, not just happy paths

Example:

```python
class TestMyFeature:
    """Tests for my new feature."""

    def setup_method(self):
        """Clear state before each test."""
        Partition.partition_by_index.clear()

    def test_feature_works(self):
        """Test that feature works correctly."""
        # Arrange
        partition = Partition(1)

        # Act
        result = partition.some_method()

        # Assert
        assert result == expected_value
```