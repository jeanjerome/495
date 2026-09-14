Feature: A verification is run twice on the same version, and one that changes its mind decides nothing
  Every other control compares two trees. This one compares two runs of one command on the same
  tree, with nothing changed in between: a command that reports success once and failure once is
  not an instrument. What it happened to report first credits no requirement and charges none —
  it neither demonstrates the behaviour nor sends the producer after a defect that will not be
  there when it looks — and the requirement waits for the requester.

  # ------------------------------------------------------------------ reading the pair

  Scenario: Two runs that both report success are one reading
    Given a first run that exited 0 printing "4 passed in 0.31s"
    And a second run that exited 0 printing "4 passed in 0.44s"
    When the harness reads the pair
    Then the command reported the same thing twice
    And the reading says "reported success twice on the same version"

  Scenario: A run that passes and a run that fails is not a reading at all
    Given a first run that exited 0 printing "4 passed in 0.31s"
    And a second run that exited 1 printing "1 failed, 3 passed"
    When the harness reads the pair
    Then the command did not report the same thing twice
    And the reading says "reported success once and failure once on the same version: exit 0 then exit 1"

  Scenario: A run that passes and a run that never finishes is not a reading either
    Given a first run that exited 0 printing "4 passed in 0.31s"
    And a second run that timed out printing "no output"
    When the harness reads the pair
    Then the command did not report the same thing twice
    And the reading says "exit 0 then timed out"

  Scenario: Two runs that fail the same way are one reading
    Given a first run that exited 1 printing "E       assert subtract(5, 3) == 2\nE       assert 8 == 2"
    And a second run that exited 1 printing "E       assert subtract(5, 3) == 2\nE       assert 8 == 2"
    When the harness reads the pair
    Then the command reported the same thing twice
    And the reading says "failed the same way twice on the same version"

  Scenario: Two runs that fail the same way at different moments are still one reading
    Given a first run that exited 1 printing "FAILED tests/test_calc.py::test_subtract in 0.31s"
    And a second run that exited 1 printing "FAILED tests/test_calc.py::test_subtract in 1.12s"
    When the harness reads the pair
    Then the command reported the same thing twice

  Scenario: Two runs that fail for two different reasons hand the producer nothing to look at
    Given a first run that exited 1 printing "E       assert subtract(5, 3) == 2\nE       assert 8 == 2"
    And a second run that exited 1 printing "E       ConnectionRefusedError: [Errno 61]"
    When the harness reads the pair
    Then the command did not report the same thing twice
    And the reading says "failed twice on the same version, for two different reasons"

  # ------------------------------------------------------------------ the decision

  Scenario: A check that reported success once and failure once credits nothing
    Given a behaviour requirement R1 verified by the test V1
    And V1 passed on the change
    And V1 did not report the same thing twice, saying "V1 reported success once and failure once on the same version: exit 0 then exit 1"
    And a reviewer accepted the change
    When the harness assesses the change
    Then the requirement R1 is undetermined
    And the reason for R1 says "no verification that reported the same thing twice"
    And the outcome is undetermined
    And a requirement was not credited: "R1: V1 passed, and did not report the same thing twice on the same version"

  Scenario: A check that failed and then passed sends the producer after nothing
    Given a behaviour requirement R1 verified by the test V1
    And V1 failed on the change
    And V1 did not report the same thing twice, saying "V1 reported success once and failure once on the same version: exit 1 then exit 0"
    And a reviewer accepted the change
    When the harness assesses the change
    Then the requirement R1 is undetermined
    And no correction was requested
    And the outcome is undetermined

  Scenario: A reviewer's finding resting on a check that changed its mind is set aside
    Given a behaviour requirement R1 verified by the test V1
    And V1 failed on the change
    And V1 did not report the same thing twice, saying "V1 reported success once and failure once on the same version: exit 1 then exit 0"
    And a reviewer reported a violation of R1 citing "V1 fails: assert 8 == 2"
    When the harness assesses the change
    Then the requirement R1 is undetermined
    And no correction was requested

  Scenario: A requirement another check demonstrates is demonstrated
    Given a behaviour requirement R1 verified by the test V1
    And R1 is also verified by the test V4
    And V1 passed on the change
    And V4 passed on the change
    And V1 did not report the same thing twice, saying "V1 reported success once and failure once on the same version: exit 0 then exit 1"
    And a reviewer accepted the change
    When the harness assesses the change
    Then the requirement R1 is satisfied
    And the outcome is accept

  Scenario: A check that reported the same thing twice decides as it always did
    Given a behaviour requirement R1 verified by the test V1
    And V1 passed on the change
    And V1 reported the same thing twice
    And a reviewer accepted the change
    When the harness assesses the change
    Then the requirement R1 is satisfied
    And the outcome is accept

  # ------------------------------------------------------------------ through the engine

  Scenario: A check that reports the same thing twice leaves the run as it was
    Given the sample project
    When a change run walks the workflow
    Then every check of iteration 1 reported the same thing twice
    And the requirement R1 is satisfied
    And the run ends delivered

  Scenario: A check that passes and then fails leaves the requirement it carries undetermined
    Given the sample project
    And a check that reports success and then failure
    When a change run walks the workflow
    Then the check of iteration 1 did not report the same thing twice
    And the requirement R3 is undetermined
    And the run's reason for R3 says "no verification that reported the same thing twice"
    And the "correctness" reviewer's prompt says "Verifications that did not report the same thing twice"
    And the run awaits the requester on an undetermined verdict
    When the requester accepts the risk with the note "the check reads a counter outside the worktree; it is the check that is wrong, not the change"
    Then the run ends delivered
    And the report says "stability_check"

  Scenario: A check that fails and then passes asks nobody to correct anything
    Given the sample project
    And a check that reports failure and then success
    When a change run walks the workflow
    Then the check of iteration 1 did not report the same thing twice
    And no correction was requested of the producer
    And the run kept to one iteration
    And the requirement R3 is undetermined
    And the run awaits the requester on an undetermined verdict

  Scenario: A check slower than a second run is worth is left alone, and said to be
    Given the sample project
    And no check is given time for a second run
    When a change run walks the workflow
    Then nothing was run a second time
    And the run warns "whether it reports the same thing twice is not measured"
    And the requirement R1 is satisfied
    And the run ends delivered

  Scenario: The requester can leave the stability check out
    Given the sample project
    And the stability check is allowed no command
    When a change run walks the workflow
    Then nothing was run a second time
    And the requirement R1 is satisfied
    And the run ends delivered
