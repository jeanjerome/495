"""Exécution bornée des processus enfants."""

from __future__ import annotations

import io
import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import IO, Any

from harness495.errors import ChangeError


# Nombre d’octets conservés par flux capturé. Le reste du flux est lu puis
# écarté, de sorte qu’un processus bavard ne bloque jamais sur un tube plein.
OUTPUT_LIMIT_BYTES = 4 * 1024 * 1024


class BoundedReader:
    """Vide un flux jusqu’à sa fermeture en conservant seulement un préfixe borné."""

    def __init__(self, stream: io.BufferedReader, limit: int) -> None:
        self.limit = limit
        self.prefix = bytearray()
        self.total = 0
        self._stream = stream
        self._thread = threading.Thread(target=self._drain, daemon=True)
        self._thread.start()

    def _drain(self) -> None:
        with self._stream as stream:
            while True:
                chunk = stream.read1(65536)
                if not chunk:
                    return
                self.total += len(chunk)
                remaining = self.limit - len(self.prefix)
                if remaining > 0:
                    self.prefix.extend(chunk[:remaining])

    def result(self) -> tuple[str, int, bool]:
        """Retourne le texte conservé, le nombre total d’octets émis et la troncature."""

        self._thread.join()
        truncated = self.total > self.limit
        data = bytes(self.prefix)
        if truncated:
            data = strip_incomplete_utf8_sequence(data)
        return data.decode("utf-8", errors="replace"), self.total, truncated


def strip_incomplete_utf8_sequence(data: bytes) -> bytes:
    """Retire une séquence UTF-8 multi-octets coupée à la fin d’un préfixe."""

    for offset in range(1, min(4, len(data)) + 1):
        byte = data[-offset]
        if byte & 0xC0 == 0x80:
            continue
        if byte & 0x80 == 0:
            return data
        if byte & 0xE0 == 0xC0:
            expected = 2
        elif byte & 0xF0 == 0xE0:
            expected = 3
        elif byte & 0xF8 == 0xF0:
            expected = 4
        else:
            return data
        return data[:-offset] if expected > offset else data
    return data


def _write_stdin(stream: IO[bytes], content: bytes) -> None:
    try:
        with stream:
            stream.write(content)
    except (BrokenPipeError, OSError):
        pass


def terminate_process_group(process: subprocess.Popen[Any]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def execute_process(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    timeout_seconds: int | None,
    stdin: str | None = None,
) -> dict[str, Any]:
    """Exécute une commande sans shell ; `timeout_seconds` à `None` ne borne pas sa durée.

    Chaque flux est vidé jusqu’à sa fermeture par un lecteur dédié qui conserve
    ses premiers `OUTPUT_LIMIT_BYTES` octets. Le résultat rapporte, par flux, le
    texte conservé, le nombre total d’octets émis et la troncature éventuelle.
    """

    started = time.monotonic()
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=environment,
            stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as error:
        raise ChangeError(
            "process", f"impossible de lancer {command[0]} : {error}"
        ) from error

    assert process.stdout is not None and process.stderr is not None
    stdout_reader = BoundedReader(process.stdout, OUTPUT_LIMIT_BYTES)
    stderr_reader = BoundedReader(process.stderr, OUTPUT_LIMIT_BYTES)
    if stdin is not None:
        assert process.stdin is not None
        threading.Thread(
            target=_write_stdin, args=(process.stdin, stdin.encode("utf-8")), daemon=True
        ).start()

    timed_out = False
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        terminate_process_group(process)
        process.wait()

    stdout, stdout_bytes, stdout_truncated = stdout_reader.result()
    stderr, stderr_bytes, stderr_truncated = stderr_reader.result()
    return {
        "command": command,
        "duration_seconds": round(time.monotonic() - started, 6),
        "exit_code": None if timed_out else process.returncode,
        "stderr": stderr,
        "stderr_bytes": stderr_bytes,
        "stderr_truncated": stderr_truncated,
        "stdout": stdout,
        "stdout_bytes": stdout_bytes,
        "stdout_truncated": stdout_truncated,
        "timed_out": timed_out,
    }
