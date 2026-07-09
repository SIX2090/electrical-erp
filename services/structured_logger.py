"""Structured JSON logger for business events.

This service provides structured (JSON) logging for key business operations
such as inventory posting, order approval, and financial transactions.
It supplements (not replaces) the existing audit_log_service and standard
Python logging.

Usage:
    from services.structured_logger import business_logger

    business_logger.log_event(
        event_type="inventory_receipt",
        entity_type="stock_transaction",
        entity_id=tx_id,
        product_id=product_id,
        quantity=quantity,
        warehouse_id=warehouse_id,
    )
"""
import json
import logging
import os
from datetime import datetime, timezone


class StructuredBusinessLogger:
    """Emit business events as JSON log lines for easy aggregation and analysis."""

    def __init__(self, name="erp.business"):
        self._logger = logging.getLogger(name)
        self._configured = False

    def _ensure_handler(self):
        """Attach a file handler for business events if not yet configured."""
        if self._configured:
            return
        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
        try:
            if not os.path.isdir(log_dir):
                os.makedirs(log_dir, exist_ok=True)
            handler = logging.FileHandler(os.path.join(log_dir, "business_events.log"), encoding="utf-8")
            handler.setLevel(logging.INFO)
            formatter = logging.Formatter("%(message)s")
            handler.setFormatter(formatter)
            self._logger.addHandler(handler)
            self._logger.setLevel(logging.INFO)
            self._logger.propagate = False
        except Exception:
            logging.getLogger(__name__).exception("Failed to configure structured business logger")
        self._configured = True

    def log_event(self, event_type, entity_type, entity_id, **kwargs):
        """Log a business event as a JSON object with timestamp and context.

        Args:
            event_type: Category of event (e.g. 'inventory_receipt', 'order_approve').
            entity_type: Type of business entity (e.g. 'stock_transaction', 'sales_order').
            entity_id: Identifier of the affected entity.
            **kwargs: Additional context fields (product_id, quantity, amount, etc.).
        """
        self._ensure_handler()
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "entity_type": entity_type,
            "entity_id": entity_id,
        }
        event.update(kwargs)
        try:
            self._logger.info(json.dumps(event, ensure_ascii=False, default=str))
        except Exception:
            logging.getLogger(__name__).exception("Failed to write structured business event")


business_logger = StructuredBusinessLogger()
