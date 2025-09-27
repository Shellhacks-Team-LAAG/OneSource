from __future__ import annotations

import logging
import sys
import uuid
import contextvars
from typing import Any, Dict


# ---- Per-request trace id ----
_trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="-")


def new_trace_id() -> str:
    """Create a short, unique trace id for one request."""
    return uuid.uuid4().hex[:8]


def bind_trace_id(tid: str) -> None:
    """Bind the trace id to the current context (request scope)."""
    _trace_id_var.set(tid)


def get_trace_id() -> str:
    """Get the current context's trace id (or '-' if none)."""
    return _trace_id_var.get()


# ---- Key=Value formatter ----
class KeyValueFormatter(logging.Formatter):
    """
    Emits single-line key=value pairs for easy grepping and log collection.
    Example:
      ts=2025-09-27T01:23:45Z level=INFO trace_id=q9c1b route=/ask timings_ms.slack=0 ...
    """

    def format(self, record: logging.LogRecord) -> str:
        # Base fields
        kv: Dict[str, Any] = {
            "level": record.levelname,
            "trace_id": getattr(record, "trace_id", get_trace_id()),
            "msg": record.getMessage(),
        }

        # Additional structured fields (optional)
        extra_kv = getattr(record, "kv", None)
        if isinstance(extra_kv, dict):
            kv.update(extra_kv)

        # Render as key=value, quoting values with spaces
        parts = []
        for k, v in kv.items():
            val = str(v)
            if " " in val or "=" in val:
                val = f"\"{val}\""
            parts.append(f"{k}={val}")
        return " ".join(parts)


# ---- Logger factory & helper ----
def get_logger(name: str = "app") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(KeyValueFormatter())
        logger.addHandler(handler)
        logger.propagate = False
    return logger


def log_kv(logger: logging.Logger, level: int, msg: str, **kv: Any) -> None:
    """
    Log a message with structured key=value fields and the bound trace_id.
    Usage:
        log_kv(LOG, logging.INFO, "ask.complete",
               route="/ask", duration_ms=123, **timings_dict)
    """
    logger.log(level, msg, extra={"kv": kv, "trace_id": get_trace_id()})