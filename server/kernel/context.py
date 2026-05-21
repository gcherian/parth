from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Event:
    type: str
    aggregate: str
    aggregate_id: str
    payload: dict
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    request_id: str = ""
    trace_id: str = ""
    schema_ver: int = 1
    ts: datetime = field(default_factory=datetime.utcnow)


@dataclass
class KernelContext:
    request_id: str
    trace_id: str
    learner_id: str
    subject: str
    grade: int
    message: str
    history: list[dict] = field(default_factory=list)
    # Filled in by modules as they run
    learner_context: str = ""
    curriculum_context: str = ""
    moderation_ok: bool = True
    distress_detected: bool = False
    module_data: dict[str, Any] = field(default_factory=dict)
    # Set by tutor.runtime
    response_text: str = ""
    model_used: str = ""
    # Database connection (injected by kernel, shared across modules in one transaction)
    db: Any = None


@dataclass
class ModuleResult:
    success: bool = True
    data: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    veto: bool = False          # only moderation.ops sets this True
    veto_response: str = ""     # pre-approved safe message to return instead
