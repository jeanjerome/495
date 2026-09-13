Feature: The report shows, under each requirement, the scenario that verifies it
  A test stated as a scenario is the text the requester approved. The Markdown report of a run
  puts that text under the requirement it verifies, next to what its command reported on the
  evaluated commit, so that the reader checks the behaviour asked for against the behaviour
  observed without opening the specification or the evidence. A requirement none of whose
  verifications carries a scenario keeps its table row and gets no section.

  Background:
    Given a run with the requirement "R1" "calc.subtract(a, b) returns a - b" verified by "V1"
    And "V1" is a test to create with the scenario given "the calc module" when "subtract(5, 3) is called" then "the result is 2"

  Scenario: A scenario that passed on the evaluated commit is shown under its requirement
    Given the requirement "R1" stands "satisfied"
    And in the current iteration "V1" passed on the evaluated commit as "ev-1"
    When the report is rendered
    Then the report has the section "### R1 PASS: calc.subtract(a, b) returns a - b"
    And under it the line "V1 (test, to create): PASS on the evaluated commit (ev-1)"
    And under it the Gherkin block "Scenario: a test | Given the calc module | When subtract(5, 3) is called | Then the result is 2"

  Scenario: A scenario that failed on the evaluated commit is shown with what the command reported
    Given the requirement "R1" stands "violated"
    And in the current iteration "V1" failed on the evaluated commit as "ev-1" reporting "exit 1: assert 8 == 2"
    When the report is rendered
    Then the report has the section "### R1 FAIL: calc.subtract(a, b) returns a - b"
    And under it the line "V1 (test, to create): FAIL on the evaluated commit (ev-1): exit 1: assert 8 == 2"

  Scenario: A scenario whose command did not run on the evaluated commit says so
    Given the requirement "R1" stands "undetermined"
    And "V1" was run on the base version only, as "ev-0"
    When the report is rendered
    Then the report has the section "### R1 UNDETERMINED: calc.subtract(a, b) returns a - b"
    And under it the line "V1 (test, to create): not run on the evaluated commit"

  Scenario: A scenario whose command reports the same with and without the change says so
    Given the requirement "R1" stands "undetermined"
    And "V1" is vacuous because "passes on the base version as well"
    And in the current iteration "V1" passed on the evaluated commit as "ev-1"
    When the report is rendered
    Then the report has the section "### R1 UNDETERMINED: calc.subtract(a, b) returns a - b"
    And under it the line "V1 (test, to create): reports the same with and without the change: passes on the base version as well"

  Scenario: A requirement whose verifications carry no scenario has no section
    Given the run also has the requirement "R2" "existing tests still pass" verified by "V2"
    And "V2" is an existing test with no scenario
    When the report is rendered
    Then the report has the row "| R2 | PENDING | existing tests still pass | V2 |"
    And the report has no section for "R2"

  Scenario: The report of a delivered run shows the scenario the requester approved and what it observed
    Given the sample project
    When a change run walks the workflow
    And the report is rendered
    Then the report has the section "### R1 PASS: calc.subtract(a, b) returns a - b"
    And under it the Gherkin block "Scenario: a test exercising subtract with positive and negative values | Given the calc module | When subtract(5, 3) and subtract(3, 5) are called | Then they return 2 and -2"
    And under it a line saying "V1 (test, to create): PASS on the evaluated commit"
    And the report has no section for "R2"
