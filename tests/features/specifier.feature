Feature: Verifications that name a catalogue role
  The specifier is given the test-library catalogue against the project's role coverage, and
  a verification names the catalogue role it measures. A role the project measures with a tool
  leaves the verification judged on its command; a role nothing in the project measures makes
  the verification insufficient, with the catalogue's recommendation in its rationale, because
  the tool is the requester's to put in place through a proposal and not the producer's to add.
  A proposal the requester declined is an answer already given: the run reads it when it is
  profiled, the specifier is told not to call for the role, and a verification that names it
  anyway cites the refusal, not a proposal to answer.

  Scenario: A verification of a role the project measures is judged on its command
    Given a profile that measures the role "property" of "python" with "hypothesis"
    And a specification with the requirement "R1" verified by "V1"
    And "V1" is a test with a command, naming the role "property"
    When the harness audits the specification against the profile
    Then the verification "V1" is "sufficient"
    And the specification states no gap

  Scenario: A verification of a role nothing measures is insufficient and names the recommendation
    Given a profile that measures no role of "python"
    And a specification with the requirement "R1" verified by "V1"
    And "V1" is a test with a command, naming the role "mutation"
    When the harness audits the specification against the profile
    Then the verification "V1" is "insufficient"
    And its rationale says "the project does not measure the mutation role (the suite detects a deliberate alteration of the code it covers); the catalogue recommends mutmut for python"
    And its rationale says "a conformance proposal for the requester (495 proposals), not part of this change"
    And the specification states the gap "R1 has no sufficient verification"

  Scenario: A requirement also carried by a verification the project can run is not a gap
    Given a profile that measures no role of "python"
    And a specification with the requirement "R1" verified by "V1, V2"
    And "V1" is a test with a command, naming the role "mutation"
    And "V2" is a test with a command, naming no role
    When the harness audits the specification against the profile
    Then the verification "V1" is "insufficient"
    And the verification "V2" is "sufficient"
    And the specification states no gap

  Scenario: A role the profile knows nothing about leaves the verification judged on its command
    Given a profile with no role coverage
    And a specification with the requirement "R1" verified by "V1"
    And "V1" is a test with a command, naming the role "property"
    When the harness audits the specification against the profile
    Then the verification "V1" is "sufficient"
    And the specification states no gap

  Scenario: The specifier receives the catalogue as a fact and the role it names stops the run at the gate
    Given the sample project
    And the scripted specifier names the role "property" on "V1"
    When a change run walks the workflow
    Then the specifier's prompt carries the fact "Test-library catalogue and the project's role coverage"
    And the specifier's prompt says "property (no counter-example to a stated invariant over a generated input range): not measured; the catalogue recommends hypothesis"
    And the specification records "V1" with the role "property"
    And the run waits at the gate with a question saying "the catalogue recommends hypothesis for python"

  Scenario: A verification of a role the requester declined cites the refusal, not a proposal to answer
    Given a profile that measures no role of "python"
    And the requester has declined the role "mutation" of "python" with the reason "the suite is too slow to mutate"
    And a specification with the requirement "R1" verified by "V1"
    And "V1" is a test with a command, naming the role "mutation"
    When the harness audits the specification against the profile
    Then the verification "V1" is "insufficient"
    And its rationale says "the requester declined mutmut for python: the suite is too slow to mutate; the decision stands, take a verification the project can run"
    And its rationale does not say "conformance proposal"

  Scenario: The run reads the declined proposals when it is profiled and tells the specifier
    Given the sample project
    And the project's proposals hold a declined one on "property" of "python" with the reason "inputs are enumerable here"
    And the scripted specifier names the role "property" on "V1"
    When a change run walks the workflow
    Then the specifier's prompt says "the catalogue recommends hypothesis, declined by the requester: inputs are enumerable here; do not call for this role"
    And the run's profile records the role "property" of "python" as declined with the reason "inputs are enumerable here"
    And the run waits at the gate with a question saying "the requester declined hypothesis for python: inputs are enumerable here"
