Feature: A test to create is specified as a scenario the requester approves
  A verification of kind test carries a scenario: what is given, what is done, what is then
  observed, in the words of the requirement. The specifier is told to write it, the audit
  makes a test to create without one insufficient, the requester reads its steps whole when
  the specification is put to approval, and the producer receives the same steps as the text
  to write the test from.

  Scenario: A test to create without a scenario is insufficient and its requirement is a gap
    Given a specification with the requirement "R1" verified by "V1"
    And "V1" is a test to create with a command and no scenario
    When the harness audits the specification
    Then the verification "V1" is "insufficient"
    And its rationale says "a test to create is stated as a scenario (given, when, then)"
    And its rationale says "none was given"
    And the specification states the gap "R1 has no sufficient verification"

  Scenario: A test to create whose scenario observes nothing is insufficient
    Given a specification with the requirement "R1" verified by "V1"
    And "V1" is a test to create with the scenario given "a calculator" when "subtract(5, 3) is called" and no then step
    When the harness audits the specification
    Then the verification "V1" is "insufficient"
    And its rationale says "its scenario has no when or then step"

  Scenario: A test to create with a complete scenario is judged on its command
    Given a specification with the requirement "R1" verified by "V1"
    And "V1" is a test to create with the scenario given "a calculator" when "subtract(5, 3) is called" then "the result is 2"
    When the harness audits the specification
    Then the verification "V1" is "sufficient"
    And the specification states no gap

  Scenario: An existing test is judged on its command, scenario or not
    Given a specification with the requirement "R1" verified by "V1"
    And "V1" is an existing test with a command and no scenario
    When the harness audits the specification
    Then the verification "V1" is "sufficient"
    And the specification states no gap

  Scenario: Several steps under one keyword read as And
    Given a scenario given "a calculator | a display" when "add(1, 2) is called" then "the display shows 3 | nothing else changes"
    When the scenario is written as Gherkin steps
    Then its steps are "Given a calculator | And a display | When add(1, 2) is called | Then the display shows 3 | And nothing else changes"

  Scenario: The specifier is told to state each test as a scenario, and the requester and the producer read its steps
    Given the sample project
    And the scripted specifier states "V1" as the scenario given "the calc module" when "subtract(5, 3) and subtract(3, 5) are called" then "they return 2 and -2"
    When a change run walks the workflow
    Then the specifier's prompt says "Every verification of kind "test" carries a `scenario`"
    And the specification records "V1" with the steps "Given the calc module | When subtract(5, 3) and subtract(3, 5) are called | Then they return 2 and -2"
    And the specification printed for approval shows "V1" with the step "Then they return 2 and -2"
    And the producer's prompt shows "V1" with the step "When subtract(5, 3) and subtract(3, 5) are called"

  Scenario: A scenario of blank steps is no scenario, and the run stops at the gate
    Given the sample project
    And the scripted specifier states "V1" as a scenario of blank steps only
    When a change run walks the workflow
    Then the specification records "V1" with no scenario
    And the run waits at the gate with a question saying "a test to create is stated as a scenario"
