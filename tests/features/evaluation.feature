Feature: Evaluating a change that already exists
  The same chain, with the producer left out: a commit, the working tree, or a patch file is
  taken as the version under evaluation, and the specification, the verifications and the
  reviews are measured against it. What the run delivers is the reading, not a change — the
  version it evaluated is the one it was given, and the patch it recorded evaluates again to
  the same thing.

  Background:
    Given a project 495 can work in

  Scenario: A commit already in the project is read without a producer being called
    Given the change is committed in the project
    When the committed change is evaluated
    Then the run is delivered, and accepted
    And no producer was called
    And the version evaluated is that commit
    And 5 interventions were charged, at a cost the agents reported

  Scenario: The working tree is evaluated, and the patch it leaves evaluates to the same thing
    Given the change is in the working tree, uncommitted
    When the working tree is evaluated
    Then the run is delivered
    And the change touched calc.py and tests/test_calc.py
    When the working tree is put back and the patch of that run is evaluated
    Then the second run is delivered, and accepted
