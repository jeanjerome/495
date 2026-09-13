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
    And the catalogue has no entry for "shell"
    When the harness profiles the project
    Then the role "static" of "shell" is not measured
    And there is no gap on "static" of "shell"

  Scenario: A shell project checked by shellcheck alone is told the rest of each entry
    Given a shell project
    And the file ".shellcheckrc" contains "disable=SC2086"
    When the harness profiles the project
    Then the gap on "static" of "shell" is "incomplete"
    And that gap recommends "shellcheck, shfmt"
    And the gap on "security" of "shell" is "incomplete"
    And that gap recommends "shellcheck, gitleaks"
    And the gap on "bdd" of "shell" is "unmeasured"
    And that gap recommends "cucumber, aruba"

  Scenario: A shell project is told kcov for its coverage, which runs through shellspec
    Given a shell project
    And the file "tests/deploy.bats" contains "@test 'it runs' { true; }"
    When the harness profiles the project
    Then the gap on "coverage" of "shell" is "unmeasured"
    And that gap recommends "kcov"
    And that gap states no condition
    And there is no gap on "runner" of "shell"

  Scenario: A shell project measuring coverage is told shellspec as its runner, with the condition
    Given a shell project
    And the file ".github/workflows/ci.yml" contains "run: ulimit -n 1024 && shellspec --kcov"
    When the harness profiles the project
    Then the role "coverage" of "shell" is measured with "kcov"
    And the catalogue rendered to the specifier says "runner (planned cases hold, through public interfaces): not measured; the catalogue recommends shellspec (the project keeps its specs in shellspec, or measures coverage, which goes through it)"

  Scenario: A shell project without specs is told bats as its runner, the default of the cell
    Given a shell project
    When the harness profiles the project
    Then the catalogue rendered to the specifier says "runner (planned cases hold, through public interfaces): not measured; the catalogue recommends bats, which the requester puts in place through a proposal"

  Scenario: A JavaScript project on Express is told the in-process contract entry
    Given a JavaScript project
    And its package.json lists the dependency "express"
    When the harness profiles the project
    Then the gap on "contract" of "javascript/typescript" is "unmeasured"
    And that gap recommends "express-openapi-validator"
    And that gap states the condition "the project uses Express"

  Scenario: A JavaScript project without Express is told the proxy, the default of the cell
    Given a JavaScript project
    When the harness profiles the project
    Then the gap on "contract" of "javascript/typescript" is "unmeasured"
    And that gap recommends "@stoplight/prism-cli"
    And that gap states no condition

  Scenario: The profile command states the gaps to the requester
    Given a Python project
    And its pyproject.toml lists the dependency "bandit"
    When the requester runs "495 profile"
    Then the output shows "Gaps against the catalogue"
    And the output shows "another tool than the catalogue's"

  Scenario: The profile command says when there is nothing to state
    Given a Ruby project
    When the requester runs "495 profile"
    Then the output shows "catalogue: no gap"

  Scenario: The profile in JSON carries the gaps
    Given a Python project
    When the requester runs "495 --json profile"
    Then the JSON output lists a gap on "fuzzing" of "python"

  Scenario: The specifier is told what each role must show, the tool in place and the recommendation
    Given a Python project
    And its pyproject.toml lists the dependency "hypothesis"
    When the harness profiles the project
    Then the catalogue rendered to the specifier says "property (no counter-example to a stated invariant over a generated input range): measured with hypothesis"
    And the catalogue rendered to the specifier says "fuzzing (no crash, hang or unbounded consumption on malformed input): not measured; the catalogue recommends atheris"

  Scenario: The specifier is told the condition under which a recommendation applies
    Given a Python project
    When the harness profiles the project
    Then the catalogue rendered to the specifier says "not measured; the catalogue recommends behave (the project has no pytest suite, or keeps its scenarios in a standalone features/ tree)"

  Scenario: The specifier is told when the catalogue has no entry for a role the project does not measure
    Given a shell project
    And the file ".shellcheckrc" contains "disable=SC2086"
    And the catalogue has no entry for "shell"
    When the harness profiles the project
    Then the catalogue rendered to the specifier says "static (lint, formatting, complexity, duplication): measured with shellcheck"
    And the catalogue rendered to the specifier says "bdd (behaviour scenarios in Gherkin (Given/When/Then), readable by the requester, bound to steps and run by the runner): not measured; the catalogue has no entry"

  Scenario: A Rust project running cargo audit keeps it and is told cargo-deny for its layers
    Given a Rust project
    And the file ".github/workflows/ci.yml" contains "run: cargo audit"
    When the harness profiles the project
    Then there is no gap on "security" of "rust"
    And the gap on "architecture" of "rust" is "unmeasured"
    And that gap recommends "cargo-deny"

  Scenario: A Rust project without an advisory check is told cargo-deny, the default of the cell
    Given a Rust project
    When the harness profiles the project
    Then the gap on "security" of "rust" is "unmeasured"
    And that gap recommends "cargo-deny"
    And that gap states no condition

  Scenario: A Go project on golangci-lint is told depguard for its layers, with the condition
    Given a Go project
    And the file ".golangci.yml" contains "linters:\n  enable: [gosec]"
    When the harness profiles the project
    Then the gap on "architecture" of "go" is "unmeasured"
    And that gap recommends "depguard"
    And that gap states the condition "the project already runs golangci-lint"
    And the gap on "security" of "go" is "incomplete"
    And that gap recommends "gosec, govulncheck"

  Scenario: A Go project without golangci-lint is told go-arch-lint, the default of the cell
    Given a Go project
    When the harness profiles the project
    Then the gap on "architecture" of "go" is "unmeasured"
    And that gap recommends "go-arch-lint"
    And that gap states no condition

  Scenario: A Kotlin project on Gradle is told the Kotlin entries, each with its condition
    Given a Kotlin project
    And its build.gradle.kts depends on "io.kotest:kotest-runner-junit5:6.2.5"
    When the harness profiles the project
    Then the gap on "property" of "java/kotlin" is "unmeasured"
    And that gap recommends "kotest-property"
    And that gap states the condition "the project runs kotest"
    And the gap on "static" of "java/kotlin" is "unmeasured"
    And that gap recommends "detekt, ktlint"
    And that gap states the condition "the project is written in Kotlin"
    And the gap on "coverage" of "java/kotlin" is "unmeasured"
    And that gap recommends "kover"

  Scenario: A Java project is told the default entries of the cells
    Given a Java project
    When the harness profiles the project
    Then the gap on "property" of "java/kotlin" is "unmeasured"
    And that gap recommends "jqwik"
    And that gap states no condition
    And the gap on "static" of "java/kotlin" is "unmeasured"
    And that gap recommends "checkstyle, PMD"
    And the gap on "coverage" of "java/kotlin" is "unmeasured"
    And that gap recommends "jacoco"

  Scenario: The specifier is told when nothing is known about the roles of the project
    Given a Ruby project
    When the harness profiles the project
    Then the catalogue rendered to the specifier says "no role coverage"
