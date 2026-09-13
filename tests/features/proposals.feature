Feature: Conformance proposals put to the requester and kept under .495
  Each gap the profile states against the catalogue becomes a proposal recorded in
  .495/proposals.json. The requester accepts, declines or defers it; an accepted proposal
  becomes a change run whose intent puts the recommended tool in place with a first test of
  the role; a declined proposal keeps its reason and is not proposed again; a proposal whose
  gap is no longer stated is resolved.

  Scenario: Each gap stated by the profile is recorded as an open proposal
    Given a Python project
    When the requester runs "495 profile"
    Then the proposal on "fuzzing" of "python" is "open"
    And that proposal states "nothing measures it; the catalogue recommends atheris"
    And the output shows "open proposal(s): answer with 495 proposals"

  Scenario: Profiling again keeps the proposal rather than opening another
    Given a Python project
    And the requester has run "495 profile"
    When the requester runs "495 profile"
    Then there is one proposal on "fuzzing" of "python"

  Scenario: The intent of a proposal asks for the tool and a first test of the role
    Given a Python project
    When the requester runs "495 profile"
    Then the intent of the proposal on "property" of "python" says "Put hypothesis in place, as docs/test-libraries.md recommends"
    And the intent of the proposal on "property" of "python" says "and write a first property-based test"

  Scenario: The intent of a proposal on a role measured with another tool keeps that tool in view
    Given a Python project
    And its pyproject.toml lists the dependency "bandit"
    When the requester runs "495 profile"
    Then the intent of the proposal on "security" of "python" says "with bandit; docs/test-libraries.md recommends ruff, pip-audit"
    And the intent of the proposal on "security" of "python" says "keep bandit unless the change makes it redundant"

  Scenario: An accepted proposal becomes a change run carrying its intent
    Given a Python project
    And the project is a git repository
    And the requester has run "495 profile"
    When the requester accepts the proposal on "fuzzing" of "python" without starting it
    Then the proposal on "fuzzing" of "python" is "accepted"
    And a run of mode "change" exists with the intent of that proposal
    And the run's intent source is "proposal"
    And the output shows "start it with: 495 run"

  Scenario: An accepted proposal is not accepted a second time while its run carries it
    Given a Python project
    And the project is a git repository
    And the requester has run "495 profile"
    And the requester has accepted the proposal on "fuzzing" of "python" without starting it
    When the requester tries to accept the proposal on "fuzzing" of "python" without starting it
    Then the command is refused with "already accepted"

  Scenario: A declined proposal keeps its reason and is shown as declined when the profile runs again
    Given a Python project
    And the requester has run "495 profile"
    When the requester declines the proposal on "mutation" of "python" with the reason "the suite is too slow to mutate"
    And the requester runs "495 profile"
    Then the proposal on "mutation" of "python" is "declined"
    And that proposal carries the reason "the suite is too slow to mutate"
    And the output shows "declined: the suite is too slow to mutate"

  Scenario: Declining needs a reason
    Given a Python project
    And the requester has run "495 profile"
    When the requester tries to decline the proposal on "mutation" of "python" without a reason
    Then the command is refused with "needs a reason"
    And the proposal on "mutation" of "python" is "open"

  Scenario: A deferred proposal stays listed and can be accepted later
    Given a Python project
    And the project is a git repository
    And the requester has run "495 profile"
    And the requester has deferred the proposal on "contract" of "python"
    When the requester accepts the proposal on "contract" of "python" without starting it
    Then the proposal on "contract" of "python" is "accepted"

  Scenario: A proposal whose gap is no longer stated is resolved
    Given a Python project
    And the requester has run "495 profile"
    When its pyproject.toml lists the dependency "hypothesis"
    And the requester runs "495 profile"
    Then the proposal on "property" of "python" is "resolved"

  Scenario: A declined proposal stays declined when its gap is no longer stated
    Given a Python project
    And the requester has run "495 profile"
    And the requester has declined the proposal on "property" of "python" with the reason "not now"
    When its pyproject.toml lists the dependency "hypothesis"
    And the requester runs "495 profile"
    Then the proposal on "property" of "python" is "declined"

  Scenario: A resolved proposal is not answered
    Given a Python project
    And the requester has run "495 profile"
    And its pyproject.toml lists the dependency "hypothesis"
    And the requester has run "495 profile"
    When the requester tries to decline the proposal on "property" of "python" with the reason "no"
    Then the command is refused with "is resolved"

  Scenario: The proposals command lists each proposal with its answer
    Given a Python project
    And the requester has run "495 profile"
    And the requester has declined the proposal on "mutation" of "python" with the reason "too slow"
    When the requester runs "495 proposals"
    Then the output shows "conformance proposals in"
    And the output shows "declined: too slow"

  Scenario: The proposals in JSON carry the gap and the answer
    Given a Python project
    And the requester has run "495 profile"
    When the requester runs "495 --json proposals"
    Then the JSON output lists a proposal on "fuzzing" of "python" with the answer starting "open:"

  Scenario: The schema of the proposals document is published
    Given a Python project
    When the requester runs "495 schema proposals"
    Then the output shows "Proposal"
