"""Trace-id aware logging helpers.

The platform persists its own trace/span records, but operational logs still
need to be correlatable with them.  A context variable carries the current
trace id and a logging filter injects it into every record, so existing
``LOGGING`` handlers keep working without callers passing ``extra`` each time.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar

_TRACE_ID: ContextVar[str] = ContextVar("modelscope_trace_id", default="-")


class TraceIdFilter(logging.Filter):
    """Attach ``trace_id`` to every record (``-`` when outside a trace)."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        record.trace_id = _TRACE_ID.get()
        return True


def current_trace_id() -> str:
    return _TRACE_ID.get()


@contextmanager
def bind_trace_id(trace_id: str):
    token = _TRACE_ID.set(str(trace_id))
    try:
        yield
    finally:
        _TRACE_ID.reset(token)
