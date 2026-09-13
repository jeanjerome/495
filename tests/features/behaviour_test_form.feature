Feature: The form of a test to create follows the project's scenario runner
  A test to create that carries a scenario is written as a feature file bound to step
  definitions where the profile measures the role bdd, and with the project's test runner
  otherwise. The producer and the test_quality reviewer read the same sentence stating that
  form, the producer is told the scenario is the text of the test, and the reviewer is told to
  compare the requirement, the scenario and the test.

  Scenario: A project binding scenarios with pytest-bdd asks for a feature file
    Given the sample project
    And its pyproject.toml lists the dependency "pytest-bdd"
    And the reviewers include "test_quality"
    When a change run walks the workflow
    Then the producer's prompt says "The project binds behaviour scenarios with pytest-bdd for python"
    And the producer's prompt says "is a `.feature` file whose scenario has the specification's steps"
    And the producer's prompt says "A verification that carries a scenario is the text of its test"
    And the "test_quality" reviewer's prompt says "The project binds behaviour scenarios with pytest-bdd for python"
    And the "test_quality" reviewer's prompt says "compare three texts"
    And the "test_quality" reviewer's prompt says "is a finding on the verification"

  Scenario: A project without a scenario runner asks for a test in its runner and no new tool
    Given the sample project
    And the reviewers include "test_quality"
    When a change run walks the workflow
    Then the producer's prompt says "The project has no tool binding behaviour scenarios"
    And the producer's prompt says "written with the project's test runner"
    And the producer's prompt says "No scenario runner is added to the project by the change"
    And the "test_quality" reviewer's prompt says "The project has no tool binding behaviour scenarios"

  Scenario: The form names every technology's scenario runner
    Given a profile measuring bdd with "pytest-bdd" for "python" and with "cucumber, aruba" for "shell"
    When the form of a behaviour test is rendered
    Then it says "The project binds behaviour scenarios with pytest-bdd for python; cucumber, aruba for shell"

  Scenario: A bdd row nothing measures is no scenario runner
    Given a profile whose bdd row for "python" is measured by nothing
    When the form of a behaviour test is rendered
    Then it says "The project has no tool binding behaviour scenarios"
