"""Vocabulaire attendu dérivé des octets historiques vérifiés."""

import hashlib
import json
from pathlib import Path


EXPECTED_DIGEST = "f503f82932ab6f6b5c172c5d7aeabb24cdf36291e2e50c0c3a207d79bb622c92"
PATH = Path("495/changes/INC-0002/requirements.json")
RAW = PATH.read_bytes()
if hashlib.sha256(RAW).hexdigest() != EXPECTED_DIGEST:
    raise AssertionError("le requirement set historique ne correspond pas aux octets attendus")
VOCABULARY = json.loads(RAW)["vocabulary"]


def values(name: str) -> set[str]:
    return set(VOCABULARY[name]["values"])


def coverage(name: str, actual: object, expected: object, cardinality: int) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: domaine observé différent du domaine attendu")
    actual_count = len(actual)  # type: ignore[arg-type]
    if actual_count != cardinality:
        raise AssertionError(f"{name}: {actual_count} valeurs au lieu de {cardinality}")
    print(f"COVERAGE {name} {actual_count}/{cardinality}")
