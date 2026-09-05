"""Primitives locales bornées utilisées par les composants persistants."""

import os
from pathlib import Path

from .model import PersistenceErrorCode, PersistenceRefusal


def ensure_directory(path: Path) -> PersistenceRefusal | None:
    candidates = tuple(reversed((path, *path.parents)))
    existing_parent_found = False
    for candidate in candidates:
        if candidate.is_symlink():
            return PersistenceRefusal(
                PersistenceErrorCode.SYMLINK_REFUSED, str(candidate)
            )
        if candidate.exists():
            existing_parent_found = True
            if not candidate.is_dir():
                return PersistenceRefusal(
                    PersistenceErrorCode.IO_ERROR, str(candidate), ("not_a_directory",)
                )
        elif existing_parent_found:
            break
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        return PersistenceRefusal(
            PersistenceErrorCode.IO_ERROR, str(path), (type(error).__name__,)
        )
    current = path
    while True:
        if current.is_symlink():
            return PersistenceRefusal(
                PersistenceErrorCode.SYMLINK_REFUSED, str(current)
            )
        if current.parent == current:
            break
        current = current.parent
    return None


def sync_directory(path: Path) -> PersistenceRefusal | None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as error:
        return PersistenceRefusal(
            PersistenceErrorCode.IO_ERROR,
            str(path),
            ("directory_sync", type(error).__name__),
        )
    return None


def refuse_symlink(path: Path) -> PersistenceRefusal | None:
    if path.is_symlink():
        return PersistenceRefusal(PersistenceErrorCode.SYMLINK_REFUSED, str(path))
    return None
