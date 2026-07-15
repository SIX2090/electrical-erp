"""Unit tests for decimal_utils.py - safe decimal conversion and money formatting."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from decimal import Decimal
from services.decimal_utils import as_decimal, money_fmt


class TestAsDecimal:
    def test_as_decimal_integer(self):
        result = as_decimal(123)
        assert result == Decimal("123")

    def test_as_decimal_float(self):
        result = as_decimal(123.45)
        assert result == Decimal("123.45")

    def test_as_decimal_string(self):
        result = as_decimal("123.45")
        assert result == Decimal("123.45")

    def test_as_decimal_decimal(self):
        result = as_decimal(Decimal("123.45"))
        assert result == Decimal("123.45")

    def test_as_decimal_none(self):
        result = as_decimal(None)
        assert result == Decimal("0")

    def test_as_decimal_none_with_default(self):
        result = as_decimal(None, "10")
        assert result == Decimal("10")

    def test_as_decimal_empty_string(self):
        result = as_decimal("")
        assert result == Decimal("0")

    def test_as_decimal_whitespace(self):
        result = as_decimal("  123.45  ")
        assert result == Decimal("123.45")

    def test_as_decimal_zero(self):
        result = as_decimal(0)
        assert result == Decimal("0")

    def test_as_decimal_negative(self):
        result = as_decimal(-123.45)
        assert result == Decimal("-123.45")

    def test_as_decimal_large_number(self):
        result = as_decimal(12345678901234567890.123456789)
        assert result == Decimal(str(12345678901234567890.123456789))

    def test_as_decimal_invalid_string(self):
        result = as_decimal("not_a_number")
        assert result == Decimal("0")

    def test_as_decimal_special_float_values(self):
        result = as_decimal(float("inf"))
        assert result == Decimal("Infinity")

        result = as_decimal(float("-inf"))
        assert result == Decimal("-Infinity")

        result = as_decimal(float("nan"))
        assert result.is_nan()

    def test_as_decimal_complex_number(self):
        result = as_decimal(1 + 2j)
        assert result == Decimal("0")

    def test_as_decimal_with_custom_default(self):
        result = as_decimal(None, "999")
        assert result == Decimal("999")

        result = as_decimal("invalid", "50")
        assert result == Decimal("50")


class TestMoneyFmt:
    def test_money_fmt_integer(self):
        result = money_fmt(123)
        assert result == "123.00"

    def test_money_fmt_float(self):
        result = money_fmt(123.45)
        assert result == "123.45"

    def test_money_fmt_string(self):
        result = money_fmt("123.45")
        assert result == "123.45"

    def test_money_fmt_decimal(self):
        result = money_fmt(Decimal("123.45"))
        assert result == "123.45"

    def test_money_fmt_none(self):
        result = money_fmt(None)
        assert result == "0.00"

    def test_money_fmt_zero(self):
        result = money_fmt(0)
        assert result == "0.00"

    def test_money_fmt_negative(self):
        result = money_fmt(-123.45)
        assert result == "-123.45"

    def test_money_fmt_thousands_separator(self):
        result = money_fmt(1234567.89)
        assert result == "1,234,567.89"

    def test_money_fmt_large_number(self):
        result = money_fmt(12345678901234567890.12)
        assert "," in result

    def test_money_fmt_small_decimal(self):
        result = money_fmt(0.01)
        assert result == "0.01"

        result = money_fmt(0.001)
        assert result == "0.00"

    def test_money_fmt_empty_string(self):
        result = money_fmt("")
        assert result == "0.00"

    def test_money_fmt_whitespace(self):
        result = money_fmt("  1234.56  ")
        assert result == "1,234.56"

    def test_money_fmt_invalid_string(self):
        result = money_fmt("not_a_number")
        assert result == "0.00"

    def test_money_fmt_special_float_values(self):
        result = money_fmt(float("inf"))
        assert result == "Infinity"

        result = money_fmt(float("-inf"))
        assert result == "-Infinity"

        result = money_fmt(float("nan"))
        assert result == "NaN"

    def test_money_fmt_more_decimal_places(self):
        result = money_fmt(123.456789)
        assert result == "123.46"

        result = money_fmt(123.454)
        assert result == "123.45"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
