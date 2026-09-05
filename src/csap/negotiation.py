"""Négociation déterministe de la version commune la plus élevée."""

import re

from .model import AdapterDescription, ProtocolAccepted, ProtocolOutcome, ProtocolRejected
from .validation import _reject
from .vocabulary import ErrorCode


_VERSION = re.compile(r"[0-9]+\.[0-9]+")


def negotiate(
    client_versions: tuple[str, ...], description: AdapterDescription
) -> ProtocolOutcome[str]:
    if not client_versions or any(
        not isinstance(item, str) or _VERSION.fullmatch(item) is None
        for item in client_versions
    ):
        return _reject(ErrorCode.INVALID_INPUT, "client_versions")
    common = set(client_versions) & set(description.protocol_versions)
    if not common:
        return _reject(ErrorCode.UNSUPPORTED_VERSION, "protocol_version")
    selected = max(common, key=lambda item: tuple(map(int, item.split("."))))
    return ProtocolAccepted(selected)
