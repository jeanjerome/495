"""Documents valides partagés par les contrôles CSAP."""

from csap import Operation, PortName, build_description


HEX_A = "a" * 64
HEX_B = "b" * 64


def reference(identifier="artifact", kind="execution_contract"):
    return {
        "artifact_id": identifier,
        "revision": 1,
        "kind": kind,
        "schema_version": "1",
        "digest": f"sha256:{HEX_A}",
    }


def description(ports=None, operations=None):
    ports = tuple(PortName) if ports is None else ports
    operations = tuple(Operation) if operations is None else operations
    return build_description(
        {
            "identity": "simulated-adapter",
            "adapter_version": "1.0.0",
            "protocol_versions": ["1.0", "1.2"],
            "ports": [item.value for item in ports],
            "operations": [item.value for item in operations],
            "platforms": ["simulated"],
            "toolchains": ["none"],
            "limits": {"operations": 100},
            "isolation_capabilities": [],
        }
    ).value


WORK = {
    Operation.PREPARE,
    Operation.START_AGENT,
    Operation.CAPTURE_CANDIDATE,
    Operation.RUN_CHECK,
    Operation.INTEGRATE,
    Operation.REQUEST_APPROVAL,
}
ATTEMPT = {Operation.START_AGENT, Operation.CAPTURE_CANDIDATE, Operation.RUN_CHECK}


def request_document(operation, *, request_id="request", key="key", payload=None, version="1.0", extensions=None):
    document = {
        "protocol_version": version,
        "request_id": request_id,
        "idempotency_key": key,
        "operation": operation.value,
        "payload": {} if payload is None else payload,
        "extensions": {} if extensions is None else extensions,
    }
    if operation in WORK:
        document["increment_id"] = "INC"
        document["contract_ref"] = reference("contract")
    if operation in ATTEMPT:
        document["attempt_id"] = "ATT"
    return document


def check_result(outcome="PASS"):
    return {
        "check_id": "unit",
        "check_ref": reference("check", "check_plan"),
        "contract_ref": reference("contract"),
        "candidate_ref": reference("candidate", "candidate"),
        "environment_ref": reference("environment", "observation"),
        "outcome": outcome,
        "requirements": [{"id": "REQ", "outcome": outcome}],
        "process": {"exit_code": 0 if outcome == "PASS" else 1, "timed_out": False},
        "evidence_refs": [f"sha256:{HEX_B}"],
        "feedback_ref": f"sha256:{HEX_B}",
    }
