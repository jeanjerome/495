"""Coordination locale du domaine, des décisions, du stockage et de CSAP."""

from domain.commands import (
    Command,
    CreateIncrementPayload,
    SealArtifactPayload,
    apply_command,
    create_increment,
    validate,
)
from domain.outcomes import Refused
from domain.state import IncrementState
from domain.vocabulary import CommandName, Gate
from persistence import (
    JournalEvent,
    LocalRepository,
    PersistenceErrorCode,
    PersistenceRefusal,
    canonical_digest,
    freeze_json,
    thaw_json,
)
from policy import EvaluationContext, Policy, evaluate_gate
from validation import FactBundle

from .codec import (
    CodecError,
    command_document,
    decode_command_document,
    decode_state_document,
    state_document,
)
from .model import (
    ApplicationAccepted,
    ApplicationErrorCode,
    ApplicationOutcome,
    ApplicationRefusal,
    ApplicationSnapshot,
    CommandEnvelope,
    CommandReceipt,
    GateEvaluation,
)
from .ports import PortRegistry


class LocalOrchestrator:
    def __init__(
        self, repository: LocalRepository, ports: PortRegistry = PortRegistry()
    ) -> None:
        self.repository = repository
        self.ports = ports

    def _persistence_refusal(
        self,
        refusal: PersistenceRefusal,
        current_state_version: int | None = None,
    ) -> ApplicationRefusal:
        code = {
            PersistenceErrorCode.COMMAND_CONFLICT: ApplicationErrorCode.COMMAND_CONFLICT,
            PersistenceErrorCode.STATE_VERSION_MISMATCH: ApplicationErrorCode.STATE_VERSION_MISMATCH,
        }.get(refusal.code, ApplicationErrorCode.PERSISTENCE_REFUSED)
        return ApplicationRefusal(
            code,
            refusal.subject,
            current_state_version,
            refusal.code.value,
            refusal.details,
        )

    def _load(
        self,
    ) -> ApplicationOutcome[tuple[ApplicationSnapshot, tuple[JournalEvent, ...]]]:
        journal = self.repository.journal.read()
        if isinstance(journal, PersistenceRefusal):
            return self._persistence_refusal(journal)
        increments: dict[str, IncrementState] = {}
        for event in journal.value.events:
            for digest in event.object_digests:
                verified = self.repository.objects.get(digest)
                if isinstance(verified, PersistenceRefusal):
                    return self._persistence_refusal(verified)
            try:
                envelope = decode_command_document(thaw_json(event.payload))
                state = decode_state_document(thaw_json(event.result))
            except CodecError as error:
                return ApplicationRefusal(
                    ApplicationErrorCode.SNAPSHOT_INVALID,
                    event.command_id,
                    journal.value.events[-1].state_version_after,
                    details=(str(error),),
                )
            coherent = (
                event.event_type == "DomainCommandApplied"
                and canonical_digest(event.payload) == event.command_digest
                and envelope.command.command_id == event.command_id
                and envelope.command.expected_state_version
                == event.expected_state_version
                and envelope.increment_id == state.increment_id
            )
            if not coherent:
                return ApplicationRefusal(
                    ApplicationErrorCode.SNAPSHOT_INVALID,
                    event.command_id,
                    journal.value.events[-1].state_version_after,
                    details=("event_binding",),
                )
            increments[state.increment_id] = state
        state_version = (
            journal.value.events[-1].state_version_after
            if journal.value.events
            else 0
        )
        return ApplicationAccepted(
            (
                ApplicationSnapshot(
                    state_version,
                    tuple(sorted(increments.items())),
                ),
                journal.value.events,
            )
        )

    def reconstruct(self) -> ApplicationOutcome[ApplicationSnapshot]:
        loaded = self._load()
        if isinstance(loaded, ApplicationRefusal):
            return loaded
        return ApplicationAccepted(loaded.value[0])

    def _domain_refusal(
        self, refusal: Refused, state_version: int
    ) -> ApplicationRefusal:
        return ApplicationRefusal(
            ApplicationErrorCode.DOMAIN_REFUSED,
            refusal.subject,
            state_version,
            refusal.code,
            refusal.details,
        )

    def execute(self, envelope: CommandEnvelope) -> ApplicationOutcome[CommandReceipt]:
        if (
            not isinstance(envelope, CommandEnvelope)
            or not isinstance(envelope.increment_id, str)
            or not envelope.increment_id
            or not isinstance(envelope.command, Command)
        ):
            return ApplicationRefusal(ApplicationErrorCode.INVALID_INPUT, "command")
        command = envelope.command
        if (
            not isinstance(command.command_id, str)
            or not command.command_id
            or not isinstance(command.name, CommandName)
            or isinstance(command.expected_state_version, bool)
            or not isinstance(command.expected_state_version, int)
            or command.expected_state_version < 0
        ):
            return ApplicationRefusal(ApplicationErrorCode.INVALID_INPUT, "command")
        if (
            command.name is CommandName.CREATE_INCREMENT
            and isinstance(command.payload, CreateIncrementPayload)
            and command.payload.increment_id != envelope.increment_id
        ):
            return ApplicationRefusal(
                ApplicationErrorCode.INVALID_INPUT, "increment_id"
            )

        loaded = self._load()
        if isinstance(loaded, ApplicationRefusal):
            return loaded
        snapshot, events = loaded.value
        document = command_document(envelope)
        command_digest = canonical_digest(freeze_json(document))
        existing = next(
            (
                event for event in events if event.command_id == command.command_id
            ),
            None,
        )
        if existing is not None:
            if existing.command_digest != command_digest:
                return ApplicationRefusal(
                    ApplicationErrorCode.COMMAND_CONFLICT,
                    command.command_id,
                    snapshot.state_version,
                    PersistenceErrorCode.COMMAND_CONFLICT.value,
                    (existing.command_digest, command_digest),
                )
            try:
                state = decode_state_document(thaw_json(existing.result))
            except CodecError as error:
                return ApplicationRefusal(
                    ApplicationErrorCode.SNAPSHOT_INVALID,
                    command.command_id,
                    snapshot.state_version,
                    details=(str(error),),
                )
            return ApplicationAccepted(
                CommandReceipt(
                    state.increment_id,
                    state,
                    existing.state_version_after,
                    snapshot.state_version,
                    True,
                )
            )
        if command.expected_state_version != snapshot.state_version:
            return ApplicationRefusal(
                ApplicationErrorCode.STATE_VERSION_MISMATCH,
                "expected_state_version",
                snapshot.state_version,
                details=(str(command.expected_state_version),),
            )

        current = snapshot.state_for(envelope.increment_id)
        if command.name is CommandName.CREATE_INCREMENT:
            if current is None:
                domain_result = create_increment(command, snapshot.state_version)
            else:
                domain_result = validate(current, command, snapshot.state_version)
        elif current is None:
            domain_result = validate(None, command, snapshot.state_version)
        else:
            domain_result = apply_command(current, command, snapshot.state_version)
        if isinstance(domain_result, Refused):
            return self._domain_refusal(domain_result, snapshot.state_version)
        state = domain_result.value
        object_writes = (
            (command.payload.raw,)
            if isinstance(command.payload, SealArtifactPayload)
            else ()
        )
        persisted = self.repository.execute(
            command_id=command.command_id,
            expected_state_version=command.expected_state_version,
            command=document,
            result=state_document(state),
            event_type="DomainCommandApplied",
            object_writes=object_writes,
        )
        if isinstance(persisted, PersistenceRefusal):
            return self._persistence_refusal(persisted, snapshot.state_version)
        record = persisted.value.command
        try:
            recorded_state = decode_state_document(thaw_json(record.result))
        except CodecError as error:
            return ApplicationRefusal(
                ApplicationErrorCode.SNAPSHOT_INVALID,
                command.command_id,
                persisted.value.projection.state_version,
                details=(str(error),),
            )
        return ApplicationAccepted(
            CommandReceipt(
                recorded_state.increment_id,
                recorded_state,
                record.state_version,
                persisted.value.projection.state_version,
                persisted.value.replayed,
            )
        )

    def evaluate(
        self,
        increment_id: str,
        gate: Gate,
        policy: Policy,
        facts: FactBundle,
        context: EvaluationContext,
    ) -> ApplicationOutcome[GateEvaluation]:
        if (
            not isinstance(increment_id, str)
            or not increment_id
            or not isinstance(gate, Gate)
            or not isinstance(policy, Policy)
            or not isinstance(facts, FactBundle)
            or not isinstance(context, EvaluationContext)
        ):
            return ApplicationRefusal(ApplicationErrorCode.INVALID_INPUT, "evaluation")
        reconstructed = self.reconstruct()
        if isinstance(reconstructed, ApplicationRefusal):
            return reconstructed
        snapshot = reconstructed.value
        if context.expected_state_version != snapshot.state_version:
            return ApplicationRefusal(
                ApplicationErrorCode.STATE_VERSION_MISMATCH,
                "expected_state_version",
                snapshot.state_version,
                details=(str(context.expected_state_version),),
            )
        state = snapshot.state_for(increment_id)
        if state is None:
            return ApplicationRefusal(
                ApplicationErrorCode.INVALID_INPUT,
                "increment_id",
                snapshot.state_version,
            )
        decision = evaluate_gate(
            state, gate, policy, facts, state.approvals, context
        )
        return ApplicationAccepted(
            GateEvaluation(increment_id, snapshot.state_version, decision)
        )
