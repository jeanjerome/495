Feature: The tests to create are written by a test designer before the producer
  A test written by the agent whose change it judges is one reasoner checking itself. When
  the approved specification says a test is to create, a test designer writes it from the
  approved scenario in an intervention of its own, on a tree where the behaviour does not
  exist; the harness commits the test files and hands them to the producer and the reviewers
  as protected files. A version of the change that modifies one is rejected on scope.

  Scenario: The test designer writes the test before the producer, from the approved scenario
    Given the sample project
    And V1 runs "tests/test_subtract.py"
    And the producer implements the behaviour and writes no test
    When a change run walks the workflow
    Then the roles were called in the order "specifier, test_designer, producer, reviewer, reviewer, reviewer"
    And the test designer's prompt says "Write the test of every verification marked `to_create`"
    And the test designer's prompt says "subtract(5, 3) and subtract(3, 5) are called"
    And the test designer's prompt says "the behaviour the tests observe is not implemented here"
    And the test design holds "tests/test_subtract.py"
    And the test design is committed on top of the version the designer was given
    And the producer's prompt says "## Tests written by the test designer"
    And the producer's prompt says "- tests/test_subtract.py"
    And the producer's prompt says "Protected paths (tests written by the test designer"
    And the producer's prompt says "V1: tests/test_subtract.py"
    And the "spec_compliance" reviewer's prompt says "## Tests written by the test designer"
    And the run ends delivered
    And the verification V1 is unconfirmed
    And the requirement R1 is satisfied
    And the report says "tests written by the test designer before the producer"

  Scenario: A producer that rewrites a designed test is rejected on scope, and the run goes on once it leaves the test alone
    Given the sample project
    And V1 runs "tests/test_subtract.py"
    And the producer first rewrites the designed test to pass whatever subtract does, then implements the behaviour and restores the test
    When a change run walks the workflow
    Then iteration 1 is rejected
    And a correction request of iteration 1 says "[scope] 1 test file(s) written by the test designer modified by the change: tests/test_subtract.py"
    And the evidence of iteration 1 has a failed scope check saying "written by the test designer modified"
    And the run ends delivered
    And the evidence of iteration 2 has a passed scope check saying "test file(s) written by the test designer are as written"

  Scenario: A file the test designer writes outside the tests is put back as it was
    Given the sample project
    And V1 runs "tests/test_subtract.py"
    And the test designer writes the test and a stub of the behaviour in "calc.py"
    And the producer implements the behaviour and writes no test
    When a change run walks the workflow
    Then the test design holds "tests/test_subtract.py"
    And the test design discarded "calc.py"
    And a warning says "the test designer wrote files that are not tests, put back as they were: calc.py"
    And the file "calc.py" at the test design's commit has no "subtract"
    And the run ends delivered

  Scenario: Without a test designer the producer writes the tests, as before
    Given the sample project
    And no test designer is configured
    When a change run walks the workflow
    Then the roles were called in the order "specifier, producer, reviewer, reviewer, reviewer"
    And there is no test design
    And the producer's prompt does not say "## Tests written by the test designer"
    And the run ends delivered

  Scenario: A specification with nothing to create calls no test designer
    Given the sample project
    And no verification is a test to create, R1 asking only that the suite go on passing
    When a change run walks the workflow
    Then the roles were called in the order "specifier, producer, reviewer, reviewer"
    And there is no test design

  Scenario: The test designer writes nothing, and the producer is told nothing about designed tests
    Given the sample project
    And the test designer writes nothing
    When a change run walks the workflow
    Then the test design holds no file
    And a warning says "the test designer wrote no test file"
    And the producer's prompt does not say "## Tests written by the test designer"
    And the run ends delivered

  Scenario: The configuration turns the test designer off with false
    When the configuration is built from
      """
      [roles]
      test_designer = false
      """
    Then the configured test designer is none

  Scenario: The configuration names the test designer's agent
    When the configuration is built from
      """
      [agents.x]
      kind = "codex"
      [roles]
      test_designer = "x"
      """
    Then the configured test designer is "x"

  Scenario: One agent for every role covers the test designer
    Given a configuration with the test designer "default"
    When the agent "codex:m" is set for every role
    Then the configured test designer is "codex:m"

  Scenario: One agent for every role leaves a switched-off test designer off
    Given a configuration with no test designer
    When the agent "codex:m" is set for every role
    Then the configured test designer is none
