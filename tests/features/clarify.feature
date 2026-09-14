Feature: The requester's decisions are taken before the specification, in rounds
  An ambiguity the specifier resolves on its own is the worst thing the harness can carry: the
  producer implements the misreading faithfully, the reviewers confirm it conforms, every check
  measures what the specification named, and the run accepts the thing nobody asked for. So the
  decisions are put to the requester first. A round is one intervention that returns the
  frontier — the questions whose prerequisites are settled — and one stop that answers all of
  them; the tree is recomputed from the answers each round and never dequeued, so a question
  already settled is never asked twice.

  # ------------------------------------------------------------------ what a round may ask

  Scenario: A question with two options and a consequence each is put to the requester
    Given a round that asks "Which timezone do the timestamps use?"
    And it offers "utc" saying "R2 states UTC and V2 asserts it"
    And it offers "local" saying "R2 states the host timezone and V2 asserts it"
    And it recommends "utc"
    When the harness reads the round
    Then the requester is asked 1 question
    And the question offers the answer "other"

  Scenario: A question with one option decides nothing and is not asked
    Given a round that asks "Should the flag be added?"
    And it offers "yes" saying "R3 appears"
    And it recommends "yes"
    When the harness reads the round
    Then the requester is asked nothing
    And the harness says it dropped a question "it offers fewer than two options"

  Scenario: An option that says nothing about the specification is not an option
    Given a round that asks "Which timezone do the timestamps use?"
    And it offers "utc" saying "R2 states UTC and V2 asserts it"
    And it offers "local" saying nothing
    And it recommends "utc"
    When the harness reads the round
    Then the requester is asked nothing
    And the harness says it dropped a question "state no consequence on the specification"

  Scenario: A recommendation that names no option is not a recommendation
    Given a round that asks "Which timezone do the timestamps use?"
    And it offers "utc" saying "R2 states UTC and V2 asserts it"
    And it offers "local" saying "R2 states the host timezone and V2 asserts it"
    And it recommends "iso"
    When the harness reads the round
    Then the requester is asked nothing
    And the harness says it dropped a question "its recommended answer names no option it offers"

  Scenario: A question already answered is dropped rather than asked again
    Given the requester answered "Which timezone do the timestamps use?" with "utc"
    And a round that asks "Which timezone do the timestamps use?"
    And it offers "utc" saying "R2 states UTC and V2 asserts it"
    And it offers "local" saying "R2 states the host timezone and V2 asserts it"
    And it recommends "utc"
    When the harness reads the round
    Then the requester is asked nothing
    And the harness says it dropped a question "it is already answered"

  Scenario: The same decision under a new identifier is still the same decision
    Given the requester answered "Which timezone do the timestamps use?" with "utc"
    And a round that asks "which timezone do the timestamps use" under the identifier "Q7"
    And it offers "utc" saying "R2 states UTC and V2 asserts it"
    And it offers "local" saying "R2 states the host timezone and V2 asserts it"
    And it recommends "utc"
    When the harness reads the round
    Then the requester is asked nothing
    And the harness says it dropped a question "it is already answered"

  # ------------------------------------------------------------------ through the engine

  Scenario: An intent with nothing left to decide costs one intervention and no stop
    Given the sample project
    When a change run walks the workflow
    Then the clarifier ran 1 time
    And the run raised no clarification decision
    And the run ends delivered

  Scenario: A round the requester answers becomes a fact for every later role
    Given the sample project
    And the requester answers the questions themselves
    And the requester is asked which timezone the timestamps use
    When a change run walks the workflow to its first stop
    Then the run awaits the requester on a clarification
    And the round puts 1 question to the requester
    When the requester answers "utc"
    And the run walks on to its next stop
    And the requester approves the specification
    And the run walks on
    Then the run records the decision "Which timezone do the timestamps use?" as "UTC"
    And the specifier's prompt says "Requester's decisions"
    And the specifier's prompt says "Which timezone do the timestamps use?"
    And the producer's prompt says "Which timezone do the timestamps use?"
    And the test designer's prompt says "Which timezone do the timestamps use?"
    And the "spec_compliance" reviewer's prompt says "Which timezone do the timestamps use?"
    And the specification carries the decision "Which timezone do the timestamps use?"
    And the report says "Decisions taken before the specification"

  Scenario: A question answered in the requester's own words travels as their words
    Given the sample project
    And the requester answers the questions themselves
    And the requester is asked which timezone the timestamps use
    When a change run walks the workflow to its first stop
    And the requester answers "other" with the note "the timezone the caller passes in"
    And the run walks on to its next stop
    Then the specifier's prompt says "the timezone the caller passes in"
    And the run records the decision "Which timezone do the timestamps use?" as "Something else"

  Scenario: A round left half-answered is refused, and the run stays where it was
    Given the sample project
    And the requester answers the questions themselves
    And the requester is asked two questions in one round
    When a change run walks the workflow to its first stop
    And the requester answers only the first question
    Then the answer is refused, saying "unanswered question(s)"
    And the run awaits the requester on a clarification

  Scenario: An answer that names no option of its question is refused
    Given the sample project
    And the requester answers the questions themselves
    And the requester is asked which timezone the timestamps use
    When a change run walks the workflow to its first stop
    And the requester answers "sidereal"
    Then the answer is refused, saying "is not one of its options"
    And the run awaits the requester on a clarification

  Scenario: Answering opens the next round, and a settled question is not asked twice
    Given the sample project
    And the requester answers the questions themselves
    And the requester is asked which timezone the timestamps use
    And the next round asks it again, and one more thing
    When a change run walks the workflow to its first stop
    And the requester answers "utc"
    And the run walks on to its next stop
    Then the run awaits the requester on a clarification
    And the round puts 1 question to the requester
    And the harness says it dropped a question "it is already answered"

  Scenario: Auto-approve takes the recommendations and records who took them
    Given the sample project
    And the requester is asked which timezone the timestamps use
    And the requester approves everything in advance
    When a change run walks the workflow
    Then the run records the decision "Which timezone do the timestamps use?" as "UTC"
    And the decision was taken by the harness
    And the run ends delivered

  Scenario: The clarification stops at its cap, and what is still open is recorded as open
    Given the sample project
    And the requester answers at most 1 round
    And every round asks something new
    And the requester approves everything in advance
    When a change run walks the workflow
    Then the clarifier ran 2 times
    And the run leaves 1 question unanswered
    And the run warns "with 1 question(s) still open"
    And the specifier's prompt says "Left unanswered"
    And the run ends delivered

  Scenario: The requester can leave the clarification out
    Given the sample project
    And the clarification is allowed no round
    And the requester is asked which timezone the timestamps use
    When a change run walks the workflow
    Then the clarifier ran 0 times
    And the run raised no clarification decision
    And the run ends delivered

  Scenario: A clarifier that fails leaves the run able to specify
    Given the sample project
    And the clarifier fails
    When a change run walks the workflow
    Then the run raised no clarification decision
    And the run warns "no decision was put to you"
    And the run ends delivered
