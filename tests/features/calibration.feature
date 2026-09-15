Feature: Every verification is run on the base version too, and one that cannot see the change decides nothing
  A command that reports the same thing with and without the change is not looking at the change:
  it either never reports success, or reports it whatever the tree holds. Either way no edit the
  producer could make would alter what it says, so the fault is in the specification and the
  question goes to the requester rather than to the producer. The base version it is measured on
  carries the change's own test files, so that the instrument is there and only what it measures
  is missing.

  # ------------------------------------------------------------------ the loud half

  Scenario: A command that fails with and without the change accuses the specification
    Given the sample project
    And the check of the new behaviour is a command that cannot run
    When a change run walks the workflow
    Then the run asks the requester about an instrument at fault
    And the fault names V1
    And the control run was made on the base version
    And no reviewer was asked to read the change
    And no correction was requested of the producer
    When the requester asks for a specification these commands can check, with the note "V1 never reaches the new code"
    Then the specification is open again and the decisions taken hold

  # ------------------------------------------------------------------ the quiet half

  Scenario: A command that would report success anyway is not proof that the change works
    Given the sample project
    And the check of the new behaviour is a command that passes on any tree
    When a change run walks the workflow
    Then the run asks the requester about an instrument at fault
    And V1 is recorded vacuous and blind to the change
    And the control run carried the change's own test files
    And no reviewer was asked to read the change
    When the requester leaves the command as proof of nothing
    And the run goes on
    Then both reviewers were asked to read the change
    And the requirement R1 is undetermined
    And the requirement R2 is satisfied

  # ------------------------------------------------------------------ the answer holds

  Scenario: Leaving a blind command is answered once and holds for the rest of the run
    Given the sample project
    And the check of the new behaviour is a command that cannot run
    And the producer gets the behaviour wrong once
    When a change run walks the workflow
    Then the run asks the requester about an instrument at fault
    When the requester leaves the command as proof of nothing
    And the run goes on
    Then the requester was asked about an instrument at fault once
    And no correction request names V1

  # ------------------------------------------------------------------ replacing the command

  Scenario: A replacement command is measured on both versions, and nothing is produced twice
    Given the sample project
    And the check of the new behaviour is a command that cannot run
    When a change run walks the workflow
    Then the run asks the requester about an instrument at fault
    When the requester replaces the command with the one that works
    And the run goes on
    Then V1 runs the command that works
    And V1 reports something else without the change
    And the requirement R1 is satisfied
    And the change was produced once
    And the run ends delivered

  Scenario: A note naming a verification that is not at fault replaces nothing
    Given the sample project
    And the check of the new behaviour is a command that cannot run
    When a change run walks the workflow
    Then the run asks the requester about an instrument at fault
    When the requester names V2, which is not at fault
    Then the harness answers "V2 is not one of the verifications at fault: V1"
    And the run is still awaiting the requester
    And V1 still runs the command that cannot run

  # ------------------------------------------------------------------ what the producer reported

  Scenario: A command the producer says worked is run on both versions before it is offered
    Given the sample project
    And the check of the new behaviour is a command that cannot run
    And the producer reports that another command worked
    When a change run walks the workflow
    Then the run asks the requester about an instrument at fault
    And the question offers the command the producer reported
