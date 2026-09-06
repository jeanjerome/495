import unittest
from dataclasses import replace

from application import (
    CodecError,
    canonical_domain_bytes,
    decode_command_document,
    decode_domain_value,
    decode_state_document,
    encode_domain_value,
    state_document,
)
from domain.attempts import start_attempt
from domain.commands import (
    ApplyGateDecisionPayload,
    CancelOperationPayload,
    CloseIncrementPayload,
    Command,
    CreateIncrementPayload,
    EvaluateGatePayload,
    ProposeArtifactPayload,
    RecordApprovalPayload,
    ReviseIncrementPayload,
    SealArtifactPayload,
    StartAttemptPayload,
    StartIntegrationPayload,
    SubmitCandidatePayload,
)
from domain.outcomes import Accepted
from domain.references import Approval, ApprovalRegistry
from domain.revisions import RevisionHistory
from domain.sealing import SealRegistry, digest_bytes
from domain.state import GateDecision, IncrementState
from domain.vocabulary import (
    ApprovalDecision,
    ArtifactKind,
    AttemptPhase,
    ChangeKind,
    CloseReason,
    CommandName,
    Gate,
    GateVerdict,
    OperationalStatus,
    Phase,
)
from tests.application.support import create_envelope, reference


class ApplicationCodecTest(unittest.TestCase):
    def rich_state(self):
        contract = reference()
        attempt = start_attempt(
            (),
            attempt_id="ATT-A",
            increment_id="INC-A",
            increment_revision=2,
            attempt_phase=AttemptPhase.CONCEPTION,
            contract_ref=contract,
            contract_sealed=True,
            entry_gate_satisfied=True,
            budget_available=True,
        )
        self.assertIsInstance(attempt, Accepted)
        approval = Approval(
            "APR-A",
            "owner",
            "maintainer",
            contract,
            "all",
            ApprovalDecision.APPROVED,
        )
        return IncrementState(
            "INC-A",
            2,
            Phase.DESIGNING,
            OperationalStatus.IDLE,
            "default",
            attempts=(attempt.value,),
            expected_destination="main",
            approvals=ApprovalRegistry((approval,)),
            revisions=RevisionHistory(((contract.artifact_id, 1),)),
            sealed=SealRegistry(((contract.artifact_id, 1, contract),)),
        )

    def test_domain_values_round_trip_with_stable_canonical_bytes(self):
        state = self.rich_state()
        document = encode_domain_value(state)
        decoded = decode_domain_value(document)
        self.assertEqual(decoded, state)
        self.assertEqual(canonical_domain_bytes(state), canonical_domain_bytes(decoded))
        self.assertEqual(decode_state_document(state_document(state)), state)

        raw = b"candidate"
        candidate = replace(
            reference("candidate"),
            kind=ArtifactKind.CANDIDATE,
            digest=digest_bytes(raw),
        )
        command = Command(
            "seal",
            CommandName.SEAL_ARTIFACT,
            2,
            SealArtifactPayload(candidate, raw, True, ChangeKind.CANDIDATE),
        )
        self.assertEqual(decode_domain_value(encode_domain_value(command)), command)

    def test_command_document_round_trips_and_rejects_unknown_content(self):
        envelope = create_envelope()
        from application import command_document

        self.assertEqual(decode_command_document(command_document(envelope)), envelope)
        with self.assertRaises(CodecError):
            decode_domain_value(
                {
                    "schema_version": "application-codec-1",
                    "value": {"$type": "Unknown"},
                }
            )
        invalid = state_document(self.rich_state()) | {"unexpected": True}
        with self.assertRaises(CodecError):
            decode_state_document(invalid)

    def test_all_domain_command_forms_round_trip(self):
        contract = reference()
        candidate = replace(contract, artifact_id="candidate", kind=ArtifactKind.CANDIDATE)
        approval = Approval(
            "APR-A",
            "owner",
            "maintainer",
            contract,
            "all",
            ApprovalDecision.APPROVED,
        )
        decision = GateDecision(
            "decision",
            Gate.G0,
            GateVerdict.FAIL,
            "engine-1",
            "sha256:policy",
            "sha256:facts",
            0,
        )
        payloads = {
            CommandName.APPLY_GATE_DECISION: ApplyGateDecisionPayload(decision, None),
            CommandName.CANCEL_OPERATION: CancelOperationPayload(True),
            CommandName.CLOSE_INCREMENT: CloseIncrementPayload(
                CloseReason.ABANDONED, Phase.CLOSED
            ),
            CommandName.CREATE_INCREMENT: CreateIncrementPayload("INC-A", "default"),
            CommandName.EVALUATE_GATE: EvaluateGatePayload(True),
            CommandName.PROPOSE_ARTIFACT: ProposeArtifactPayload(True, True),
            CommandName.RECORD_APPROVAL: RecordApprovalPayload(approval, True),
            CommandName.REVISE_INCREMENT: ReviseIncrementPayload(Phase.SPECIFYING),
            CommandName.SEAL_ARTIFACT: SealArtifactPayload(
                candidate, b"candidate", True
            ),
            CommandName.START_ATTEMPT: StartAttemptPayload(
                "ATT-A", AttemptPhase.CLARIFICATION, contract, True, True, True
            ),
            CommandName.START_INTEGRATION: StartIntegrationPayload(
                candidate, "main", Phase.INTEGRATING
            ),
            CommandName.SUBMIT_CANDIDATE: SubmitCandidatePayload(candidate, True),
        }
        self.assertEqual(set(payloads), set(CommandName))
        for index, (name, payload) in enumerate(payloads.items()):
            with self.subTest(name=name):
                command = Command(f"command-{index}", name, 0, payload)
                self.assertEqual(
                    decode_domain_value(encode_domain_value(command)), command
                )

    def test_codec_rejects_wrong_field_types_and_unregistered_values(self):
        encoded = encode_domain_value(self.rich_state())
        encoded["value"]["revision"] = True
        with self.assertRaises(CodecError):
            decode_domain_value(encoded)
        with self.assertRaises(CodecError):
            encode_domain_value({"arbitrary": "mapping"})
