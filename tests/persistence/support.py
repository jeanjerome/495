"""Valeurs d'appui pour les contrôles de persistance."""

from persistence import EventDraft, freeze_json


def draft(
    command_id: str = "command-1", expected_state_version: int = 0
) -> EventDraft:
    return EventDraft(
        command_id=command_id,
        command_digest=(
            "sha256:"
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        ),
        expected_state_version=expected_state_version,
        event_type="CommandApplied",
        payload=freeze_json({"command": command_id}),
        result=freeze_json({"accepted": True}),
    )
