"""Pytest configuration for ERP test suite."""
import pytest
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def pytest_configure(config):
    """Configure custom markers."""
    config.addinivalue_line(
        "markers", "unit: Unit tests (isolated, no database)"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests (database required)"
    )
    config.addinivalue_line(
        "markers", "slow: Slow tests (may take >1s)"
    )
    config.addinivalue_line(
        "markers", "financial: Financial calculation tests"
    )
    config.addinivalue_line(
        "markers", "inventory: Inventory management tests"
    )
    config.addinivalue_line(
        "markers", "traceability: Document traceability tests"
    )
    config.addinivalue_line(
        "markers", "mrp: Material requirement planning tests"
    )


def pytest_collection_modifyitems(config, items):
    """Auto-mark tests based on file names."""
    for item in items:
        # Auto-mark based on module name
        if "decimal" in item.module.__name__:
            item.add_marker(pytest.mark.unit)
        elif "trace_engine" in item.module.__name__:
            item.add_marker(pytest.mark.unit)
            item.add_marker(pytest.mark.traceability)
        elif "inventory_service" in item.module.__name__:
            item.add_marker(pytest.mark.unit)
            item.add_marker(pytest.mark.inventory)
        elif "cost_engine" in item.module.__name__:
            item.add_marker(pytest.mark.unit)
            item.add_marker(pytest.mark.financial)
        elif "mrp_engine" in item.module.__name__:
            item.add_marker(pytest.mark.unit)
            item.add_marker(pytest.mark.mrp)


@pytest.fixture(scope="session")
def test_prefix():
    """Test data prefix for isolation."""
    return "TEST"


@pytest.fixture(scope="session")
def decimal_precision():
    """Decimal precision for financial calculations."""
    from decimal import Decimal, getcontext
    getcontext().prec = 28
    return Decimal


@pytest.fixture
def mock_db():
    """Mock database connection for unit tests."""
    from unittest.mock import Mock
    mock = Mock()
    mock.query_db = Mock(return_value=[])
    mock.execute_db = Mock(return_value=1)
    mock.execute_and_return = Mock(return_value={"id": 1})
    return mock