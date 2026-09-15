Feature: The questions a run stops on, and what an answer does to it
  A run that cannot go on by itself stops and asks, rather than choosing on the requester's
  behalf. Each question carries what is needed to answer it — the specification itself, the
  output a command produced, what each option does to the run — and each answer is recorded
  against the run as the human decision it was. An answer that changes the run's own conditions
  takes effect before the run is asked the same thing again, and an option already taken is not
  offered twice.

  Background:
    Given a project 495 can work in

  # ------------------------------------------------------- approving what was specified

  Scenario: The specification put up for approval is readable, on disk and in the question
    Given approval is not automatic
    When the run is carried out
    Then the run stops on an "approve_spec" question
    And the specification is on disk, holding R1 and R2
    And the question names the path the specification is at
    And the question carries the specification itself, holding R1 and R2

  Scenario: A command invented for the specification is run once before approval is asked
    Given approval is not automatic
    When the run is carried out
    Then the run stops on an "approve_spec" question
    And the only verification run on the base version is V1
    And what it reported is judged by nobody, and kept under a reference
    And the question says what V1 did on the base version
    And the question carries the preflight, naming V1
    When the requester answers "approve", and the run is carried out
    Then the run is delivered

  Scenario: A question a handler answers inline never stops the run
    Given approval is not automatic
    And a handler that answers every question with "approve"
    When the run is carried out
    Then the handler was asked the "approve_spec" question, and nothing else
    And the run is delivered

  # ------------------------------------------------------- a requirement nothing can settle

  Scenario: A requirement only a review speaks for is a gap, and leaves the outcome undetermined
    Given approval is not automatic
    And the only verification of R1 is a review
    When the run is carried out
    Then the run stops on an "approve_spec" question
    And the specification names R1 as a gap
    And the answer "approve_with_gaps" is among those offered
    When the requester answers "approve_with_gaps", and the run is carried out
    Then the run stops on an "undetermined" question
    And the requirement R1 is undetermined
    And the outcome is undetermined
    When the requester answers "accept_with_risk" saying "reviewed by hand", and the run is carried out
    Then the run is delivered
    And the decision is recorded as taken by a human, answering "accept_with_risk"

  # ------------------------------------------------------- what the run is allowed to spend

  Scenario: A budget that runs out is put to the requester, and raising it carries the run on
    Given a budget one intervention fits into and two do not
    When the run is carried out
    Then the run stops on a "budget" question
    When the requester answers "raise" saying "1.0", and the run is carried out
    Then the run is delivered
    And the budget now stands above 1.0 dollars

  # ------------------------------------------------------- a command the machine cannot run

  Scenario: A command the project declares and the machine cannot run is put to the requester
    Given the project's test command is a tool that is not installed
    When the run is carried out
    Then the run stops on a "readiness" question
    When the requester answers "drop", and the run is carried out
    Then the profile holds no command
    And the run carried on past the gate

  # The network is opened by an answer and by nothing else, and an answer already taken stops
  # being offered: a question that came back with the same four options would be asking the
  # requester to take a step the run has already taken.
  Scenario: A baseline that fails offline can be answered by opening the network, once
    Given approval is not automatic
    And the project's test command passes only with the network open
    When the run is carried out
    Then the run stops on a "readiness" question
    And the answers offered are: proceed, allow_network, retry, abort
    And every answer says what it does to the run
    And the question records the network as closed
    And the output of the base version is kept, and names "test_needs_network"
    When the requester answers "allow_network"
    Then the network stands open on the run, which goes back to be profiled again
    And the run warns that the network was opened
    When the run is carried out
    Then the run stops on a "readiness" question
    And the answers offered are: proceed, retry, abort
    And the question no longer says "sandbox denies network access"
    And the question records the network as open
    When the requester answers "proceed"
    Then the run stands profiled
