"""Structured (JSON) logging.

Every log line is a single JSON object that carries the current request's
``correlation_id`` (see :mod:`mylife.core.context`), so logs are traceable from
connector import through to a user-facing insight.
"""

import json
import logging

from mylife.core.context import get_correlation_id, get_span_id, get_trace_id


class JsonFormatter(logging.Formatter):
    """Format log records as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, str | None] = {
            "time": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": get_correlation_id(),
            "trace_id": get_trace_id(),
            "span_id": get_span_id(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(level: str = "INFO") -> None:
    """Install the JSON formatter on the root logger.

    Idempotent: replaces existing handlers so repeated calls (e.g. one per app
    instance in tests) do not stack duplicate handlers.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
