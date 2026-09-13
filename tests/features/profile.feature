Feature: Role coverage of a host project
  For each role of the test-library catalogue, the profile names the tool the project
  measures it with, read from its manifests, its configuration and its test files, and says
  what the tool was recognised from. A role nothing measures is listed as not measured. A
  technology the profile has no markers for yet has no rows at all.

  Scenario: A dependency names the tool of a role
    Given a Python project
    And its pyproject.toml lists the dependency "hypothesis"
    When the harness profiles the project
    Then the role "property" of "python" is measured with "hypothesis"
    And that role is recognised from "pyproject.toml: dependency hypothesis"

  Scenario: A requirements file names the tool of a role
    Given a Python project
    And the file "requirements-dev.txt" contains "schemathesis>=4"
    When the harness profiles the project
    Then the role "contract" of "python" is measured with "schemathesis"
    And that role is recognised from "requirements-dev.txt: dependency schemathesis"

  Scenario: What the tests import names the tool
    Given a Python project
    And the file "tests/test_props.py" contains "from hypothesis import given"
    When the harness profiles the project
    Then the role "property" of "python" is measured with "hypothesis"
    And that role is recognised from "tests/test_props.py: from hypothesis import"

  Scenario: A configuration section names the tool
    Given a Python project
    And its pyproject.toml has the section "[tool.mutmut]"
    When the harness profiles the project
    Then the role "mutation" of "python" is measured with "mutmut"
    And that role is recognised from "pyproject.toml: [tool.mutmut]"

  Scenario: Every role of the catalogue is listed, measured or not
    Given a Python project
    When the harness profiles the project
    Then every role of the catalogue for "python" is listed
    And the role "fuzzing" of "python" is not measured

  Scenario: The pytest integration of coverage.py names coverage.py, not a second engine
    Given a Python project
    And its pyproject.toml lists the dependency "pytest-cov"
    When the harness profiles the project
    Then the role "coverage" of "python" is measured with "coverage.py"

  Scenario: Selecting ruff's S rules measures security, alongside pip-audit run in CI
    Given a Python project
    And its pyproject.toml selects the ruff rules "E, S"
    And the file ".github/workflows/ci.yml" contains "run: pip-audit"
    When the harness profiles the project
    Then the role "security" of "python" is measured with "ruff, pip-audit"
    And the role "static" of "python" is measured with "ruff"

  Scenario: A role measured with another tool than the catalogue's names that tool
    Given a Python project
    And its pyproject.toml lists the dependency "bandit"
    When the harness profiles the project
    Then the role "security" of "python" is measured with "bandit"

  Scenario: A tool that measures a role is part of the tooling the agents are told about
    Given a Python project
    And its pyproject.toml lists the dependency "pytest-bdd"
    When the harness profiles the project
    Then the tooling names "pytest-bdd"
    And the profile rendered to the agents says "python bdd: pytest-bdd"
    And the profile rendered to the agents says "python fuzzing: not measured"

  Scenario: A shell project measures its roles with the tools recognised in its tree
    Given a shell project
    And the file ".shellcheckrc" contains "disable=SC2086"
    And the file "tests/deploy.bats" contains "@test 'it runs' { true; }"
    When the harness profiles the project
    Then the role "runner" of "shell" is measured with "bats"
    And the role "static" of "shell" is measured with "shellcheck"
    And the role "bdd" of "shell" is not measured

  Scenario: A helper script's tools are named, but do not make shell a covered technology
    Given a Python project
    And the file "scripts/deploy.sh" contains "#!/bin/sh"
    And the file ".shellcheckrc" contains "disable=SC2086"
    When the harness profiles the project
    Then the tooling names "shellcheck"
    And no role coverage is listed for "shell"

  Scenario: A technology without markers has no coverage rows
    Given a Rust project
    When the harness profiles the project
    Then no role coverage is listed for "rust"
