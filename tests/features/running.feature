Feature: A verification command is run on the exact version being evaluated
  The only part of the chain that executes anything. What the command reported becomes the
  evidence of that verification on that commit: the exit code against the one expected, the
  output kept whole under a reference, and the fingerprint of that output. A worktree that has
  moved off the version under evaluation is not measured at all, and a verification with no
  command to run is recorded as not executed rather than as a failure.

  Scenario: What a command reported on the evaluated version becomes its evidence
    Given a produced version
    When "V1" runs "echo hello && exit 3" on the evaluated version, expecting exit 3
    Then the evidence says the verification passed
    And the evidence records exit 3
    And the evidence names the requirement "R1"
    And the output stored under the evidence says "hello"
    And the evidence carries the fingerprint of that output

  Scenario: A worktree that is no longer at the evaluated version is not measured
    Given a produced version
    When "V1" runs "echo hello" against a version the worktree is not at
    Then the run is refused as a version mismatch

  Scenario: A verification with no command to run is recorded as not executed
    Given a produced version
    When "V2" has no command to run
    Then the evidence says nothing about the change
    And the evidence summary says "not executed"
