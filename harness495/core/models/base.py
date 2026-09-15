"""What every model of the vocabulary rests on: a strict base, a clock and an identifier mint.

``StrictModel`` refuses a field the code does not declare and validates on assignment, so a
document that no longer matches the model is rejected at load rather than read half-way.
``SCHEMA_VERSION`` is stamped on every root document the harness writes, and ``new_id`` mints
the identifiers a run links its objects by.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict

SCHEMA_VERSION = 1


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(microsecond=0)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
