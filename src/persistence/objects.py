"""Magasin immutable d'objets adressés par leurs octets exacts."""

import hashlib
import os
import re
import tempfile
from pathlib import Path

from .filesystem import ensure_directory, refuse_symlink, sync_directory
from .model import (
    Persisted,
    PersistenceErrorCode,
    PersistenceOutcome,
    PersistenceRefusal,
    StoredObject,
)


_DIGEST = re.compile(r"sha256:([0-9a-f]{64})")


def digest_bytes(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


class ObjectStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.directory = self.root / "objects" / "sha256"

    def _path(self, digest: str) -> Path | PersistenceRefusal:
        match = _DIGEST.fullmatch(digest)
        if match is None:
            return PersistenceRefusal(PersistenceErrorCode.INVALID_DIGEST, digest)
        return self.directory / match.group(1)

    def put(self, raw: bytes) -> PersistenceOutcome[StoredObject]:
        if not isinstance(raw, bytes):
            return PersistenceRefusal(
                PersistenceErrorCode.INVALID_INPUT, "raw", ("bytes_required",)
            )
        directory_error = ensure_directory(self.directory)
        if directory_error is not None:
            return directory_error
        digest = digest_bytes(raw)
        path = self._path(digest)
        if isinstance(path, PersistenceRefusal):
            return path
        symlink_error = refuse_symlink(path)
        if symlink_error is not None:
            return symlink_error
        if path.exists():
            try:
                existing = path.read_bytes()
            except OSError as error:
                return PersistenceRefusal(
                    PersistenceErrorCode.IO_ERROR,
                    str(path),
                    (type(error).__name__,),
                )
            if existing != raw:
                return PersistenceRefusal(
                    PersistenceErrorCode.OBJECT_COLLISION, digest
                )
            return Persisted(
                StoredObject(digest, len(raw), path.relative_to(self.root).as_posix(), True)
            )

        descriptor = -1
        temporary_name = ""
        try:
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=".object-", dir=self.directory
            )
            with os.fdopen(descriptor, "wb") as stream:
                descriptor = -1
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary_name, path)
            except FileExistsError:
                symlink_error = refuse_symlink(path)
                if symlink_error is not None:
                    return symlink_error
                existing = path.read_bytes()
                if existing != raw:
                    return PersistenceRefusal(
                        PersistenceErrorCode.OBJECT_COLLISION, digest
                    )
                return Persisted(
                    StoredObject(
                        digest,
                        len(raw),
                        path.relative_to(self.root).as_posix(),
                        True,
                    )
                )
            sync_error = sync_directory(self.directory)
            if sync_error is not None:
                return sync_error
        except OSError as error:
            return PersistenceRefusal(
                PersistenceErrorCode.IO_ERROR,
                str(path),
                (type(error).__name__,),
            )
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if temporary_name:
                try:
                    Path(temporary_name).unlink(missing_ok=True)
                except OSError:
                    pass
        return Persisted(
            StoredObject(digest, len(raw), path.relative_to(self.root).as_posix(), False)
        )

    def get(self, digest: str) -> PersistenceOutcome[bytes]:
        path = self._path(digest)
        if isinstance(path, PersistenceRefusal):
            return path
        directory_error = ensure_directory(self.directory)
        if directory_error is not None:
            return directory_error
        symlink_error = refuse_symlink(path)
        if symlink_error is not None:
            return symlink_error
        if not path.is_file():
            return PersistenceRefusal(PersistenceErrorCode.OBJECT_MISSING, digest)
        try:
            raw = path.read_bytes()
        except OSError as error:
            return PersistenceRefusal(
                PersistenceErrorCode.IO_ERROR, str(path), (type(error).__name__,)
            )
        if digest_bytes(raw) != digest:
            return PersistenceRefusal(PersistenceErrorCode.OBJECT_CORRUPT, digest)
        return Persisted(raw)
