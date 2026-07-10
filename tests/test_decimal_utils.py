"""Unit tests for decimal_utils.py - critical utility for financial calculations."""
import pytest
from decimal import Decimal, InvalidOperation
from services.decimal_utils import as_decimal, money_fmt


class TestAsDecimal:
    """Tests for as_decimal conversion function."""

    def test_valid_integer(self):
        """Convert integer to Decimal."""
        result = as_decimal(100)
        assert result == Decimal("100")
        assert isinstance(result, Decimal)

    def test_valid_float(self):
        """Convert float to Decimal."""
        result = as_decimal(12.5)
        assert result == Decimal("12.5")

    def test_valid_string(self):
        """Convert string to Decimal."""
        result = as_decimal("123.45")
        assert result == Decimal("123.45")

    def test_none_value_uses_default(self):
        """None should return default."""
        result = as_decimal(None, "50")
        assert result == Decimal("50")

    def test_none_value_default_zero(self):
        """None with no default returns zero."""
        result = as_decimal(None)
        assert result == Decimal("0")

    def test_empty_string_uses_default(self):
        """Empty string should use default."""
        result = as_decimal("", "25")
        assert result == Decimal("25")

    def test_invalid_string_uses_default(self):
        """Invalid numeric string uses default."""
        result = as_decimal("abc", "10")
        assert result == Decimal("10")

    def test_scientific_notation(self):
        """Handle scientific notation."""
        result = as_decimal("1e5")
        assert result == Decimal("100000")

    def test_negative_number(self):
        """Handle negative numbers."""
        result = as_decimal("-50.5")
        assert result == Decimal("-50.5")

    def test_large_precision(self):
        """Handle high precision decimals."""
        result = as_decimal("0.12345678901234567890")
        assert result == Decimal("0.12345678901234567890")

    def test_whitespace_string(self):
        """Whitespace in string should be handled."""
        result = as_decimal("  100.5  ")
        assert result == Decimal("100.5")


class TestMoneyFmt:
    """Tests for money_fmt formatting function."""

    def test_positive_integer(self):
        """Format positive integer."""
        result = money_fmt(1000)
        assert result == "1,000.00"

    def test_positive_decimal(self):
        """Format positive decimal."""
        result = money_fmt(1234.56)
        assert result == "1,234.56"

    def test_negative_value(self):
        """Format negative value."""
        result = money_fmt(-500)
        assert result == "-500.00"

    def test_zero(self):
        """Format zero."""
        result = money_fmt(0)
        assert result == "0.00"

    def test_none_returns_zero(self):
        """None returns 0.00."""
        result = money_fmt(None)
        assert result == "0.00"

    def test_empty_returns_zero(self):
        """Empty string returns 0.00."""
        result = money_fmt("")
        assert result == "0.00"

    def test_large_number(self):
        """Format large number with multiple commas."""
        result = money_fmt(1000000)
        assert result == "1,000,000.00"

    def test_very_large_number(self):
        """Format very large number."""
        result = money_fmt(123456789.01)
        assert result == "123,456,789.01"

    def test_small_decimal(self):
        """Format small decimal values."""
        result = money_fmt(0.01)
        assert result == "0.01"

    def test_precision_truncation(self):
        """High precision truncated to 2 decimals."""
        result = money_fmt(100.999)
        assert result == "101.00"

    def test_decimal_object_input(self):
        """Accept Decimal objects."""
        result = money_fmt(Decimal("1234.56"))
        assert result == "1,234.56"

    def test_string_input(self):
        """Accept string numeric input."""
        result = money_fmt("500.25")
        assert result == "500.25"

    def test_invalid_string_returns_zero(self):
        """Invalid string returns 0.00."""
        result = money_fmt("invalid")
        assert result == "0.00"


class TestDecimalPrecisionEdgeCases:
    """Edge cases for decimal precision in financial contexts."""

    def test_accumulated_small_values(self):
        """Test accumulated rounding errors don't occur."""
        # This is critical for inventory weighted-average cost
        total = Decimal("0")
        for _ in range(1000):
            total += as_decimal("0.001")
        # Should be exactly 1.000, not 0.999 or 1.001
        assert total == Decimal("1.000")

    def test_division_precision(self):
        """Division should maintain precision."""
        result = as_decimal("100") / as_decimal("3")
        # Should not truncate arbitrarily
        assert abs(result - Decimal("33.333333")) < Decimal("0.0001")

    def test_multiplication_precision(self):
        """Multiplication of decimals."""
        unit_cost = as_decimal("12.3456")
        quantity = as_decimal("100")
        total = unit_cost * quantity
        assert total == Decimal("1234.56")

    def test_weighted_average_calculation(self):
        """Simulate weighted-average cost calculation."""
        # Existing: 100 units @ $10
        existing_qty = as_decimal("100")
        existing_cost = as_decimal("10")
        # New receipt: 50 units @ $15
        new_qty = as_decimal("50")
        new_cost = as_decimal("15")
        # Weighted average = (100*10 + 50*15) / (100+50) = 11.666...
        total_qty = existing_qty + new_qty
        total_value = (existing_qty * existing_cost) + (new_qty * new_cost)
        avg_cost = total_value / total_qty
        avg_formatted = money_fmt(avg_cost)
        assert avg_formatted == "11.67"