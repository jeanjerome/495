Feature: A run walks an intent to a change the harness accepts on its own evidence
  One intent becomes a specification, a set of tests, a change, the evidence those tests
  reported on it and the reviews of it — in that order, each role called once per iteration and
  given only what its perspective is entitled to. A version the evidence or a reviewer condemns
  is corrected and measured again; a version that repeats the one before it stops the run rather
  than paying for a second reading of the same patch. Nothing reaches the requester's checkout:
  what a run delivers is a branch and the documents that say what was observed on it.

  Background:
    Given a project 495 can work in

  # ------------------------------------------------------- the whole walk, once

  Scenario: An intent walks to a delivered change, every role having had its turn
    When the run is carried out
    Then the run is delivered, and accepted
    And every requirement is satisfied
    And the project's own test command was run on the base version
    And the roles were called in order: clarifier, specifier, test_designer, producer, reviewer, reviewer, reviewer
    And a reviewer was given the diff and the established facts, and never the producer's transcript
    And the change is a commit on the run's own branch, with the fingerprint of its patch
    And every command result is bound to that commit
    And the change touched calc.py, tests/test_calc.py and tests/test_subtract.py
    And the test designer is recorded as having written tests/test_subtract.py
    And the evidence holds 2 command results, 3 review verdicts and a scope check
    And every command that ran reported success
    And 7 interventions were charged, at a cost the agents reported
    And the decisions taken were: approve_spec, acceptance
    And the patch and the report are on disk, and the run document validates against its schema
    And the events name run.delivered and version.frozen
    And nothing was merged into the project, and the run's branch is there

  # ------------------------------------------------------- a version that does not hold

  Scenario: A rejected version is corrected, and the second one is accepted
    Given the producer writes a wrong version, then a good one
    And the correctness reviewer rejects the first version, then accepts
    When the run is carried out
    Then the run is delivered, and accepted
    And the iterations came out: reject, accept
    And a correction request of the first iteration names the requirement R1
    And the second producer was given the correction requests and the reviewer findings
    And the second version is a different commit from the first
    And a patch is on disk for each iteration

  Scenario: The correction a producer is given carries the observation, never the remedy
    Given the producer writes a wrong version, then a good one
    And the correctness reviewer rejects the first version, then accepts
    When the run is carried out
    Then the second producer was told "subtract adds instead of subtracting"
    And the second producer was told "calc.py:8"
    And the second producer was not told "use a - b"
    And the second producer was not told "make verification pass"
    And the second producer was told what is not demonstrated, or what was observed

  Scenario: A version touching a file outside the scope is rejected, and the next one lands
    Given the producer writes outside the allowed paths, then back inside them
    When the run is carried out
    Then the first iteration was rejected
    And a correction request of the first iteration names the scope and README.md
    And the run is delivered, the second iteration accepted

  # ------------------------------------------------------- a run that cannot go on

  Scenario: Reaching the iteration limit is put to the requester, and stopping rejects the change
    Given the producer writes a wrong version
    And the correctness reviewer rejects the change
    And the iteration limit is 1
    When the run is carried out
    Then the run stops on an "iteration_limit" question
    When the requester answers "stop"
    Then the run is rejected, with the outcome reject

  Scenario: A second version identical to the first stops the run instead of being read again
    Given the producer writes the same wrong version twice
    And the correctness reviewer rejects the change
    And the producer says it is blocked by "V1 cannot pass without editing files outside the scope"
    And the iteration limit is 3
    When the run is carried out
    Then the run stops on a "no_progress" question
    And the producer was called twice
    And the run holds 2 iterations
    And the two versions carry the same patch fingerprint
    And the second iteration was read by no reviewer
    And what the producer said it could not do reaches the requester, in the iteration and in the question
    And the question is one sentence, and every option says what it does to the run
    When the requester answers "stop"
    Then the run is rejected

  Scenario: A run interrupted mid-production is paused, and resumes where it stopped
    Given the producer is interrupted after writing the change
    When the run is carried out
    Then the run is paused, and will resume as ready
    And one intervention is recorded as interrupted
    When the producer is put back to normal and the run is carried out again
    Then the run is delivered
    And the iterations are numbered 1, 2
