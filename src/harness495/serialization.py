"""Sérialisation et empreintes communes aux résultats de 495."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from harness495.errors import ChangeError


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True) + "\n").encode()


def sha256_bytes(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ChangeError("precondition", f"{label} absent : {path}") from error
    except (OSError, UnicodeError) as error:
        raise ChangeError("precondition", f"{label} illisible : {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise ChangeError(
            "configuration", f"{label} contient un JSON invalide : {error}"
        ) from error
