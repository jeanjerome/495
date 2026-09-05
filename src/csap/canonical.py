"""Valeurs JSON immuables et empreinte canonique des enveloppes CSAP."""

import hashlib
import json
import math
from dataclasses import dataclass
from typing import TypeAlias


@dataclass(frozen=True, slots=True)
class JsonObject:
    items: tuple[tuple[str, "FrozenJson"], ...]


@dataclass(frozen=True, slots=True)
class JsonArray:
    items: tuple["FrozenJson", ...]


JsonScalar: TypeAlias = None | bool | int | float | str
FrozenJson: TypeAlias = JsonScalar | JsonObject | JsonArray


class InvalidJsonValue(ValueError):
    """La valeur ne possède pas de représentation JSON canonique."""


def freeze_json(value: object) -> FrozenJson:
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise InvalidJsonValue("non_finite_number")
        return value
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise InvalidJsonValue("non_string_key")
        return JsonObject(
            tuple(sorted((key, freeze_json(child)) for key, child in value.items()))
        )
    if isinstance(value, (list, tuple)):
        return JsonArray(tuple(freeze_json(child) for child in value))
    raise InvalidJsonValue(type(value).__name__)


def thaw_json(value: FrozenJson) -> object:
    if isinstance(value, JsonObject):
        return {key: thaw_json(child) for key, child in value.items}
    if isinstance(value, JsonArray):
        return [thaw_json(child) for child in value.items]
    return value


def canonical_bytes(value: FrozenJson) -> bytes:
    return json.dumps(
        thaw_json(value),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_digest(value: FrozenJson) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()
