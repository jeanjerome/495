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

  Scenario: Aruba scenarios measure the bdd role of a shell project
    Given a shell project
    And the file "Gemfile" contains "gem 'aruba'"
    And the file "features/support/env.rb" contains "require 'aruba/cucumber'"
    And the file "features/greet.feature" contains "Feature: Greeting"
    When the harness profiles the project
    Then the role "bdd" of "shell" is measured with "cucumber, aruba"
    And that role is recognised from "Gemfile: dependency aruba"

  Scenario: A secrets scan in CI measures the security role of a shell project with shellcheck
    Given a shell project
    And the file ".shellcheckrc" contains "disable=SC2086"
    And the file ".github/workflows/ci.yml" contains "uses: gitleaks/gitleaks-action@v2"
    When the harness profiles the project
    Then the role "security" of "shell" is measured with "shellcheck, gitleaks"
    And the role "static" of "shell" is measured with "shellcheck"

  Scenario: A JavaScript project's package.json names the tools of its roles
    Given a JavaScript project
    And its package.json lists the development dependency "vitest"
    And its package.json lists the development dependency "@stryker-mutator/core"
    And the file "tests/math.test.ts" contains "const f = vi.fn();"
    When the harness profiles the project
    Then the role "runner" of "javascript/typescript" is measured with "vitest"
    And that role is recognised from "package.json: dependency vitest"
    And the role "mutation" of "javascript/typescript" is measured with "@stryker-mutator/core"
    And the role "doubles" of "javascript/typescript" is measured with "vi"
    And that role is recognised from "tests/math.test.ts: vi.fn("
    And the role "fuzzing" of "javascript/typescript" is not measured

  Scenario: An npm audit in a package.json script measures the security role
    Given a JavaScript project
    And its package.json has the script "check" running "npm audit --audit-level=high"
    When the harness profiles the project
    Then the role "security" of "javascript/typescript" is measured with "npm audit"
    And that role is recognised from "package.json: npm audit"

  Scenario: A helper script's tools are named, but do not make shell a covered technology
    Given a Python project
    And the file "scripts/deploy.sh" contains "#!/bin/sh"
    And the file ".shellcheckrc" contains "disable=SC2086"
    When the harness profiles the project
    Then the tooling names "shellcheck"
    And no role coverage is listed for "shell"

  Scenario: A Rust crate's manifests name the tools of its roles
    Given a Rust project
    And its Cargo.toml lists the dev-dependency "proptest"
    And the file "deny.toml" contains "[advisories]\n[bans]\ndeny = []"
    And the file "tests/props.rs" contains "use proptest::prelude::*;"
    When the harness profiles the project
    Then the role "runner" of "rust" is measured with "cargo test"
    And the role "property" of "rust" is measured with "proptest"
    And that role is recognised from "Cargo.toml: dependency proptest"
    And the role "architecture" of "rust" is measured with "cargo-deny"
    And that role is recognised from "deny.toml: [bans]"
    And the role "security" of "rust" is measured with "cargo-deny"
    And the role "fuzzing" of "rust" is not measured

  Scenario: A fuzz crate measures the fuzzing role of a Rust project
    Given a Rust project
    And the file "fuzz/Cargo.toml" contains "[dependencies]\nlibfuzzer-sys = '0.4'"
    When the harness profiles the project
    Then the role "fuzzing" of "rust" is measured with "cargo-fuzz"
    And that role is recognised from "fuzz/Cargo.toml: dependency libfuzzer-sys"

  Scenario: A Go module's go.mod and test functions name the tools of its roles
    Given a Go project
    And its go.mod requires "pgregory.net/rapid"
    And the file "mathx/mathx_test.go" contains "func FuzzParsePair(f *testing.F) {}\nfunc BenchmarkClamp(b *testing.B) {}"
    And the file ".golangci.yml" contains "linters:\n  enable: [gosec, depguard]"
    When the harness profiles the project
    Then the role "runner" of "go" is measured with "go test"
    And the role "property" of "go" is measured with "rapid"
    And that role is recognised from "go.mod: dependency pgregory.net/rapid"
    And the role "fuzzing" of "go" is measured with "go test -fuzz"
    And that role is recognised from "mathx/mathx_test.go: func Fuzz"
    And the role "performance" of "go" is measured with "go test -bench"
    And the role "static" of "go" is measured with "golangci-lint"
    And the role "security" of "go" is measured with "gosec"
    And the role "architecture" of "go" is measured with "depguard"
    And the role "mutation" of "go" is not measured

  Scenario: A technology without markers has no coverage rows
    Given a Ruby project
    When the harness profiles the project
    Then no role coverage is listed for "ruby"
