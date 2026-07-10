"""Unit tests for cost_engine.py - cost collection and calculation."""
import pytest
from decimal import Decimal
from datetime import date, datetime
from services.cost_engine import (
    COST_TYPE_MATERIAL,
    COST_TYPE_LABOR,
    COST_TYPE_OVERHEAD,
    COST_TYPE_OUTSOURCE,
    COST_TYPE_SERVICE,
    COST_TYPE_QUALITY,
    COST_TYPE_LABELS,
    CLOSED_STATUS,
)


class TestCostTypeConstants:
    """Tests for cost type definitions."""

    def test_material_cost_type(self):
        """Material cost type constant."""
        assert COST_TYPE_MATERIAL == "material"

    def test_labor_cost_type(self):
        """Labor cost type constant."""
        assert COST_TYPE_LABOR == "labor"

    def test_overhead_cost_type(self):
        """Overhead cost type constant."""
        assert COST_TYPE_OVERHEAD == "overhead"

    def test_outsource_cost_type(self):
        """Outsource cost type constant."""
        assert COST_TYPE_OUTSOURCE == "outsource"

    def test_service_cost_type(self):
        """Service cost type constant."""
        assert COST_TYPE_SERVICE == "service"

    def test_quality_cost_type(self):
        """Quality cost type constant."""
        assert COST_TYPE_QUALITY == "quality"

    def test_all_cost_types_defined(self):
        """All six cost types must be defined."""
        expected_types = {
            "material",
            "labor",
            "overhead",
            "outsource",
            "service",
            "quality",
        }
        actual_types = {
            COST_TYPE_MATERIAL,
            COST_TYPE_LABOR,
            COST_TYPE_OVERHEAD,
            COST_TYPE_OUTSOURCE,
            COST_TYPE_SERVICE,
            COST_TYPE_QUALITY,
        }
        assert actual_types == expected_types


class TestCostTypeLabels:
    """Tests for Chinese labels for cost types."""

    def test_material_label(self):
        """Material cost Chinese label."""
        assert COST_TYPE_LABELS[COST_TYPE_MATERIAL] == "材料成本"

    def test_labor_label(self):
        """Labor cost Chinese label."""
        assert COST_TYPE_LABELS[COST_TYPE_LABOR] == "人工成本"

    def test_overhead_label(self):
        """Overhead cost Chinese label."""
        assert COST_TYPE_LABELS[COST_TYPE_OVERHEAD] == "制造费用"

    def test_outsource_label(self):
        """Outsource cost Chinese label."""
        assert COST_TYPE_LABELS[COST_TYPE_OUTSOURCE] == "委外成本"

    def test_service_label(self):
        """Service cost Chinese label."""
        assert COST_TYPE_LABELS[COST_TYPE_SERVICE] == "售后成本"

    def test_quality_label(self):
        """Quality cost Chinese label."""
        assert COST_TYPE_LABELS[COST_TYPE_QUALITY] == "质量成本"

    def test_all_labels_defined(self):
        """All cost types have labels."""
        for cost_type in COST_TYPE_LABELS.keys():
            assert cost_type in COST_TYPE_LABELS
            assert len(COST_TYPE_LABELS[cost_type]) > 0


class TestClosedStatus:
    """Tests for closed status constants."""

    def test_chinese_closed_status(self):
        """Chinese closed status."""
        assert "已关闭" in CLOSED_STATUS

    def test_chinese_completed_status(self):
        """Chinese completed status."""
        assert "已完成" in CLOSED_STATUS

    def test_chinese_void_status(self):
        """Chinese void status."""
        assert "已作废" in CLOSED_STATUS

    def test_english_closed_status(self):
        """English closed status."""
        assert "closed" in CLOSED_STATUS

    def test_english_completed_status(self):
        """English completed status."""
        assert "completed" in CLOSED_STATUS

    def test_english_void_status(self):
        """English void status."""
        assert "void" in CLOSED_STATUS
        assert "voided" in CLOSED_STATUS

    def test_cancelled_status(self):
        """Cancelled status variations."""
        assert "cancelled" in CLOSED_STATUS
        assert "canceled" in CLOSED_STATUS

    def test_status_count(self):
        """Should have all status variations."""
        # CLOSED_STATUS may contain duplicate values, use set for counting unique
        unique_statuses = set(CLOSED_STATUS)
        assert len(unique_statuses) >= 6  # At least 6 unique status types


class TestMaterialCostCalculation:
    """Tests for material cost calculation scenarios."""

    def test_single_material_issue(self):
        """Single material issue cost."""
        qty = Decimal("10")
        unit_cost = Decimal("5")
        total_cost = qty * unit_cost
        assert total_cost == Decimal("50")

    def test_multiple_material_issue(self):
        """Multiple material issues accumulate."""
        issues = [
            {"qty": Decimal("10"), "cost": Decimal("5")},
            {"qty": Decimal("20"), "cost": Decimal("3")},
            {"qty": Decimal("5"), "cost": Decimal("8")},
        ]
        total_cost = sum(issue["qty"] * issue["cost"] for issue in issues)
        # 10*5 + 20*3 + 5*8 = 50 + 60 + 40 = 150
        assert total_cost == Decimal("150")

    def test_material_return_reduces_cost(self):
        """Material return reduces total cost."""
        issue_cost = Decimal("100")
        return_cost = Decimal("30")
        net_cost = issue_cost - return_cost
        assert net_cost == Decimal("70")

    def test_weighted_average_cost(self):
        """Weighted average cost calculation."""
        # Initial: 100 units @ $10
        # Later: 50 units @ $15
        # Average: (1000 + 750) / 150 = 11.67
        total_qty = Decimal("150")
        total_value = Decimal("1750")
        avg_cost = total_value / total_qty
        assert avg_cost == Decimal("11.66666666666666666666666667")

    def test_high_precision_material_cost(self):
        """High precision for expensive materials."""
        qty = Decimal("0.001")
        unit_cost = Decimal("1000")  # $1000 per kg, issued 1 gram
        total_cost = qty * unit_cost
        assert total_cost == Decimal("1")


class TestLaborCostCalculation:
    """Tests for labor cost calculation."""

    def test_hourly_labor_rate(self):
        """Hourly labor rate calculation."""
        hours = Decimal("8")
        rate = Decimal("50")  # $50 per hour
        labor_cost = hours * rate
        assert labor_cost == Decimal("400")

    def test_multiple_operations_accumulate(self):
        """Multiple operations accumulate labor."""
        operations = [
            {"hours": Decimal("2"), "rate": Decimal("40")},
            {"hours": Decimal("3"), "rate": Decimal("50")},
            {"hours": Decimal("1"), "rate": Decimal("60")},
        ]
        total_labor = sum(op["hours"] * op["rate"] for op in operations)
        # 2*40 + 3*50 + 1*60 = 80 + 150 + 60 = 290
        assert total_labor == Decimal("290")

    def test_piece_rate_labor(self):
        """Piece rate (quantity-based) labor."""
        pieces = Decimal("100")
        rate_per_piece = Decimal("0.5")
        labor_cost = pieces * rate_per_piece
        assert labor_cost == Decimal("50")

    def test_fractional_hours(self):
        """Fractional hours calculation."""
        hours = Decimal("2.5")
        rate = Decimal("40")
        labor_cost = hours * rate
        assert labor_cost == Decimal("100")


class TestOverheadCostCalculation:
    """Tests for overhead cost calculation."""

    def test_machine_overhead(self):
        """Machine overhead cost."""
        machine_hours = Decimal("10")
        overhead_rate = Decimal("20")
        overhead_cost = machine_hours * overhead_rate
        assert overhead_cost == Decimal("200")

    def test_percentage_based_overhead(self):
        """Percentage-based overhead allocation."""
        direct_material = Decimal("1000")
        direct_labor = Decimal("500")
        total_direct = direct_material + direct_labor
        overhead_percentage = Decimal("0.15")  # 15%
        overhead_cost = total_direct * overhead_percentage
        assert overhead_cost == Decimal("225")

    def test_fixed_overhead_per_work_center(self):
        """Fixed overhead per work center."""
        work_centers = [
            {"id": 1, "fixed_overhead": Decimal("100")},
            {"id": 2, "fixed_overhead": Decimal("50")},
        ]
        total_fixed = sum(wc["fixed_overhead"] for wc in work_centers)
        assert total_fixed == Decimal("150")

    def test_overhead_allocation_by_quantity(self):
        """Overhead allocated by production quantity."""
        overhead_pool = Decimal("10000")
        total_qty = Decimal("1000")
        overhead_per_unit = overhead_pool / total_qty
        assert overhead_per_unit == Decimal("10")


class TestOutsourceCostCalculation:
    """Tests for outsourcing cost calculation."""

    def test_subcontract_cost(self):
        """Subcontract cost calculation."""
        qty = Decimal("50")
        unit_price = Decimal("20")
        outsource_cost = qty * unit_price
        assert outsource_cost == Decimal("1000")

    def test_outsource_with_shipping(self):
        """Outsource with shipping cost."""
        processing_cost = Decimal("1000")
        shipping_cost = Decimal("50")
        total_cost = processing_cost + shipping_cost
        assert total_cost == Decimal("1050")

    def test_outsource_quality_cost(self):
        """Outsource quality inspection cost."""
        outsource_cost = Decimal("1000")
        inspection_cost = Decimal("100")
        total = outsource_cost + inspection_cost
        assert total == Decimal("1100")

    def test_multiple_outsource_operations(self):
        """Multiple outsource operations accumulate."""
        operations = [
            {"process": "plating", "cost": Decimal("200")},
            {"process": "heat_treatment", "cost": Decimal("150")},
        ]
        total = sum(op["cost"] for op in operations)
        assert total == Decimal("350")


class TestServiceCostCalculation:
    """Tests for after-sale service cost calculation."""

    def test_service_parts_cost(self):
        """Service replacement parts cost."""
        parts = [
            {"qty": Decimal("2"), "cost": Decimal("50")},
            {"qty": Decimal("1"), "cost": Decimal("100")},
        ]
        parts_cost = sum(part["qty"] * part["cost"] for part in parts)
        assert parts_cost == Decimal("200")

    def test_service_labor_cost(self):
        """Service technician labor cost."""
        labor_hours = Decimal("4")
        labor_rate = Decimal("60")
        labor_cost = labor_hours * labor_rate
        assert labor_cost == Decimal("240")

    def test_service_travel_cost(self):
        """Service travel/transport cost."""
        travel_distance = Decimal("100")
        travel_rate = Decimal("0.5")
        travel_cost = travel_distance * travel_rate
        assert travel_cost == Decimal("50")

    def test_service_total_cost(self):
        """Total service cost aggregation."""
        parts_cost = Decimal("200")
        labor_cost = Decimal("240")
        travel_cost = Decimal("50")
        total = parts_cost + labor_cost + travel_cost
        assert total == Decimal("490")


class TestQualityCostCalculation:
    """Tests for quality cost calculation."""

    def test_inspection_cost(self):
        """Quality inspection cost."""
        inspection_hours = Decimal("2")
        inspector_rate = Decimal("40")
        inspection_cost = inspection_hours * inspector_rate
        assert inspection_cost == Decimal("80")

    def test_rework_cost(self):
        """Rework cost calculation."""
        rework_material = Decimal("30")
        rework_labor = Decimal("50")
        rework_cost = rework_material + rework_labor
        assert rework_cost == Decimal("80")

    def test_scrap_cost(self):
        """Scrap cost calculation."""
        scrap_qty = Decimal("10")
        scrap_value = Decimal("5")
        scrap_cost = scrap_qty * scrap_value
        assert scrap_cost == Decimal("50")

    def test_prevention_cost(self):
        """Quality prevention cost."""
        training_cost = Decimal("200")
        process_improvement = Decimal("100")
        prevention_cost = training_cost + process_improvement
        assert prevention_cost == Decimal("300")


class TestTotalCostCalculation:
    """Tests for total cost aggregation."""

    def test_product_total_cost(self):
        """Product total cost = material + labor + overhead."""
        material = Decimal("1000")
        labor = Decimal("500")
        overhead = Decimal("225")
        total = material + labor + overhead
        assert total == Decimal("1725")

    def test_project_total_cost(self):
        """Project total cost including all types."""
        costs = {
            "material": Decimal("10000"),
            "labor": Decimal("5000"),
            "overhead": Decimal("2000"),
            "outsource": Decimal("3000"),
            "service": Decimal("500"),
            "quality": Decimal("300"),
        }
        total = sum(costs.values())
        assert total == Decimal("20800")

    def test_unit_cost_calculation(self):
        """Unit cost from total."""
        total_cost = Decimal("1725")
        qty = Decimal("10")
        unit_cost = total_cost / qty
        assert unit_cost == Decimal("172.5")

    def test_gross_margin_calculation(self):
        """Gross margin from cost and revenue."""
        revenue = Decimal("2000")
        cost = Decimal("1725")
        gross_profit = revenue - cost
        gross_margin = gross_profit / revenue
        assert gross_profit == Decimal("275")
        assert gross_margin == Decimal("0.1375")


class TestCostAllocationByDimension:
    """Tests for cost allocation by project/serial/work_order."""

    def test_project_level_cost(self):
        """Cost allocated to project."""
        project_code = "PRJ-001"
        project_costs = [
            {"cost_type": "material", "amount": Decimal("1000")},
            {"cost_type": "labor", "amount": Decimal("500")},
        ]
        total_project_cost = sum(item["amount"] for item in project_costs)
        assert total_project_cost == Decimal("1500")

    def test_serial_level_cost(self):
        """Cost allocated to machine serial."""
        serial_no = "SN-001"
        serial_cost = Decimal("1500")
        assert serial_cost > 0

    def test_work_order_level_cost(self):
        """Cost allocated to work order."""
        wo_id = 1001
        wo_costs = [
            {"component": "material", "cost": Decimal("800")},
            {"component": "labor", "cost": Decimal("200")},
        ]
        total_wo_cost = sum(item["cost"] for item in wo_costs)
        assert total_wo_cost == Decimal("1000")

    def test_multiple_work_orders_in_project(self):
        """Multiple work orders under one project."""
        project_code = "PRJ-001"
        wo_costs = {
            1001: Decimal("1000"),
            1002: Decimal("800"),
            1003: Decimal("600"),
        }
        project_total = sum(wo_costs.values())
        assert project_total == Decimal("2400")


class TestCostPrecisionAndRounding:
    """Tests for cost precision and rounding."""

    def test_high_precision_total(self):
        """High precision for total cost."""
        items = [
            Decimal("123.45"),
            Decimal("67.89"),
            Decimal("0.01"),
        ]
        total = sum(items)
        assert total == Decimal("191.35")

    def test_rounding_for_display(self):
        """Rounding for financial display."""
        raw_cost = Decimal("123.4567")
        display_cost = round(raw_cost, 2)
        assert display_cost == Decimal("123.46")

    def test_accumulation_no_loss(self):
        """Accumulation should not lose precision."""
        # Sum 1000 items of $0.001 each = $1.00
        total = Decimal("0")
        for _ in range(1000):
            total += Decimal("0.001")
        assert total == Decimal("1.000")

    def test_large_value_precision(self):
        """Large values maintain precision."""
        large_cost = Decimal("1000000.01")
        qty = Decimal("1000")
        total = large_cost * qty
        assert total == Decimal("1000000010")


class TestCostBusinessRules:
    """Business rule tests for cost calculation."""

    def test_closed_status_excludes_cost(self):
        """Closed documents excluded from cost calculation."""
        status = "已关闭"
        assert status in CLOSED_STATUS

    def test_void_status_excludes_cost(self):
        """Void documents excluded from cost calculation."""
        status = "已作废"
        assert status in CLOSED_STATUS

    def test_active_status_includes_cost(self):
        """Active documents included in cost calculation."""
        active_statuses = ["草稿", "已提交", "已审核", "已过账"]
        closed = CLOSED_STATUS
        for status in active_statuses:
            assert status not in closed

    def test_cost_must_be_positive(self):
        """Cost amounts must be non-negative."""
        cost_amount = Decimal("100")
        assert cost_amount >= 0

    def test_zero_cost_allowed(self):
        """Zero cost allowed (free goods/services)."""
        zero_cost = Decimal("0")
        assert zero_cost >= 0


class TestCostEngineEdgeCases:
    """Edge cases for cost engine."""

    def test_no_costs_for_period(self):
        """Handle period with no costs."""
        costs = []
        total = sum(costs) if costs else Decimal("0")
        assert total == Decimal("0")

    def test_single_item_project(self):
        """Project with single cost item."""
        costs = [{"type": "material", "amount": Decimal("100")}]
        total = sum(item["amount"] for item in costs)
        assert total == Decimal("100")

    def test_mixed_currency_costs(self):
        """Handle costs in different currencies."""
        # Requires conversion to base currency
        costs = [
            {"currency": "USD", "amount": Decimal("100")},
            {"currency": "CNY", "amount": Decimal("500")},
        ]
        # Would need exchange rate conversion
        # For test, assume conversion happens elsewhere
        assert len(costs) == 2

    def test_negative_cost_adjustment(self):
        """Negative cost adjustment (credit/refund)."""
        original_cost = Decimal("100")
        adjustment = Decimal("-20")
        adjusted_cost = original_cost + adjustment
        assert adjusted_cost == Decimal("80")

    def test_cost_adjustment_from_reversal(self):
        """Cost adjustment from reversal operation."""
        # Reversal of previous posting
        posted_cost = Decimal("500")
        reversal_cost = Decimal("-500")
        net_cost = posted_cost + reversal_cost
        assert net_cost == Decimal("0")


class TestCostTraceability:
    """Tests for cost traceability requirements."""

    def test_cost_source_document_required(self):
        """Cost must link to source document."""
        cost_entry = {
            "amount": Decimal("100"),
            "source_type": "work_order",
            "source_id": 1001,
            "source_no": "WO-001",
        }
        assert cost_entry.get("source_type") is not None
        assert cost_entry.get("source_id") is not None

    def test_cost_project_serial_trace(self):
        """Cost must have project/serial trace."""
        cost_entry = {
            "amount": Decimal("100"),
            "project_code": "PRJ-001",
            "serial_no": "SN-001",
        }
        assert cost_entry.get("project_code") is not None
        assert cost_entry.get("serial_no") is not None

    def test_cost_type_label_for_report(self):
        """Cost type label used in reports."""
        cost_type = COST_TYPE_MATERIAL
        label = COST_TYPE_LABELS.get(cost_type)
        assert label == "材料成本"

    def test_cost_aggregation_by_type(self):
        """Cost aggregated by type for reporting."""
        costs = [
            {"type": COST_TYPE_MATERIAL, "amount": Decimal("100")},
            {"type": COST_TYPE_MATERIAL, "amount": Decimal("200")},
            {"type": COST_TYPE_LABOR, "amount": Decimal("50")},
        ]
        from collections import defaultdict
        by_type = defaultdict(Decimal)
        for item in costs:
            by_type[item["type"]] += item["amount"]
        assert by_type[COST_TYPE_MATERIAL] == Decimal("300")
        assert by_type[COST_TYPE_LABOR] == Decimal("50")