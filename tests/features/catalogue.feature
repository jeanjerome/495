Feature: Gaps of a host project against the test-library catalogue
  The profile compares the role coverage with the catalogue and states each gap: a role
  nothing measures, a role measured with another tool than the recommended one, a role
  measured with part of the recommended entry. Only the roles whose measure can contradict
  the agent's implementation are compared, and only where the catalogue has an entry; a cell
  with several entries takes the one whose condition holds in the project.

  Scenario: A role nothing measures is a gap naming the recommended tool
    Given a Python project
    When the harness profiles the project
    Then the gap on "fuzzing" of "python" is "unmeasured"
    And that gap recommends "atheris"
    And that gap reads "nothing measures it; the catalogue recommends atheris"

  Scenario: A role measured with another tool than the catalogue's is a gap naming both
    Given a Python project
    And its pyproject.toml lists the dependency "bandit"
    When the harness profiles the project
    Then the gap on "security" of "python" is "other_tool"
    And that gap recommends "ruff, pip-audit"
    And that gap reads "measured with bandit; the catalogue recommends ruff, pip-audit"

  Scenario: A role measured with part of the recommended entry says what is missing
    Given a Python project
    And its pyproject.toml lists the dependency "pytest-cov"
    When the harness profiles the project
    Then the gap on "coverage" of "python" is "incomplete"
    And that gap reads "measured with coverage.py; the catalogue recommends coverage.py, diff-cover: diff-cover missing"

  Scenario: A role measured with the recommended tool is not a gap
    Given a Python project
    And its pyproject.toml lists the dependency "hypothesis"
    When the harness profiles the project
    Then there is no gap on "property" of "python"

  Scenario: A role that cannot contradict the agent's implementation is never a gap
    Given a Python project
    When the harness profiles the project
    Then the role "doubles" of "python" is not measured
    And there is no gap on "doubles" of "python"
    And there is no gap on "runner" of "python"
    And there is no gap on "performance" of "python"

  Scenario: A project with pytest tests is told pytest-bdd, the default of the cell
    Given a Python project
    And its pyproject.toml lists the dependency "pytest"
    When the harness profiles the project
    Then the gap on "bdd" of "python" is "unmeasured"
    And that gap recommends "pytest-bdd"
    And that gap states no condition

  Scenario: A project without a pytest suite is told behave, with the condition that selects it
    Given a Python project
    When the harness profiles the project
    Then the gap on "bdd" of "python" is "unmeasured"
    And that gap recommends "behave"
    And that gap states the condition "the project has no pytest suite, or keeps its scenarios in a standalone features/ tree"

  Scenario: behave in a standalone features tree next to a pytest suite is not a gap
    Given a Python project
    And its pyproject.toml lists the dependency "pytest"
    And its pyproject.toml lists the dependency "behave"
    And the file "features/steps/steps.py" contains "from behave import given"
    When the harness profiles the project
    Then there is no gap on "bdd" of "python"

  Scenario: behave without a features tree next to a pytest suite is told pytest-bdd
    Given a Python project
    And its pyproject.toml lists the dependency "pytest"
    And its pyproject.toml lists the dependency "behave"
    When the harness profiles the project
    Then the gap on "bdd" of "python" is "other_tool"
    And that gap recommends "pytest-bdd"

  Scenario: A technology whose section of the catalogue is empty has no gaps
    Given a shell project
    When the harness profiles the project
    Then the role "static" of "shell" is not measured
    And there is no gap on "static" of "shell"

  Scenario: The profile command states the gaps to the requester
    Given a Python project
    And its pyproject.toml lists the dependency "bandit"
    When the requester runs "495 profile"
    Then the output shows "Gaps against the catalogue"
    And the output shows "another tool than the catalogue's"

  Scenario: The profile command says when there is nothing to state
    Given a Rust project
    When the requester runs "495 profile"
    Then the output shows "catalogue: no gap"

  Scenario: The profile in JSON carries the gaps
    Given a Python project
    When the requester runs "495 --json profile"
    Then the JSON output lists a gap on "fuzzing" of "python"
