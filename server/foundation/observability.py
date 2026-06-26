import logging
import uuid
from contextvars import ContextVar
from typing import Any

import structlog

_request_id_var: ContextVar[str] = ContextVar("request_id", default="")
_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


def set_request_context(request_id: str, trace_id: str):
    _request_id_var.set(request_id)
    _trace_id_var.set(trace_id)


def get_request_id() -> str:
    return _request_id_var.get()


def get_trace_id() -> str:
    return _trace_id_var.get()


def _add_request_context(logger, method, event_dict: dict) -> dict:
    rid = _request_id_var.get()
    tid = _trace_id_var.get()
    if rid:
        event_dict["request_id"] = rid
    if tid:
        event_dict["trace_id"] = tid
    return event_dict


def configure_logging(level: str = "INFO"):
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _add_request_context,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
    )


def get_logger(name: str) -> Any:
    # Bind the logger name as a field since PrintLogger has no .name attribute
    return structlog.get_logger().bind(logger=name)
