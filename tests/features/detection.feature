Feature: What a project is written in, and the commands that already check it
  Before anything is specified, the harness reads the project's manifests, its configuration
  and its tree: the technologies it is written in, the commands that already check it, the
  tools it is kept honest with, and the documents that describe it. A command the requester
  declared wins over one the harness derived. Shell is the stack with no manifest, so its
  files are the only evidence there is, and a helper script beside another stack names the
  tools it uses without making the project shell.

  Scenario: Several manifests are read, and the stack detected first names the test command
    Given a Python project
    And its pyproject.toml lists the dependency "pytest"
    And its pyproject.toml lists the dependency "ruff"
    And its pyproject.toml has the section "[tool.mypy]"
    And its package.json has the script "test" running "vitest"
    And its package.json has the script "lint" running "eslint ."
    And its Makefile has the target "build"
    And the file "CONTRIBUTING.md" contains "be nice"
    When the harness profiles the project
    Then the languages are "python, javascript/typescript"
    And the command "test" ends with "pytest -q"
    And the command "lint" ends with "ruff check ."
    And the command "typecheck" ends with "mypy ."
    And the command "build" is "make build"
    And the documentation files name "CONTRIBUTING.md"
    And the excerpt of "CONTRIBUTING.md" is "be nice"

  Scenario: Shell is detected wherever the scripts are kept
    Given the file "scripts/deploy.sh" contains "#!/bin/sh\necho deploying"
    When the harness profiles the project
    Then the languages are "shell"

  Scenario: A script shipped by a dependency is not the project
    Given the file "node_modules/pkg/install.sh" contains "#!/bin/sh"
    And the file ".cache/leftover.sh" contains "#!/bin/sh"
    When the harness profiles the project
    Then no language is detected

  Scenario: A helper script beside another stack does not make the project shell
    Given a Python project
    And its pyproject.toml lists the dependency "pytest"
    And the file "scripts/deploy.sh" contains "#!/bin/sh\necho deploying"
    And the file "run.sh" contains "#!/bin/sh\nexec python -m x"
    When the harness profiles the project
    Then the languages are "python"

  Scenario: A shellcheck configuration names the lint of a shell project
    Given a shell project
    And the file ".shellcheckrc" contains "disable=SC2086"
    When the harness profiles the project
    Then the tooling names "shellcheck"
    And the command "lint" is "shellcheck $(git ls-files '*.sh')"

  Scenario: A directive left in a script is the commoner evidence that shellcheck is run
    Given a shell project
    And the file "bin/release.sh" contains "#!/bin/sh\n# shellcheck disable=SC2086\nrm $files"
    When the harness profiles the project
    Then the tooling names "shellcheck"

  Scenario: bats is run where its tests are
    Given a shell project
    And the file "tests/deploy.bats" contains "@test 'it runs' {\n  true\n}"
    When the harness profiles the project
    Then the tooling names "bats"
    And the command "test" is "bats tests"

  Scenario: An indent style every editor reads names no formatter
    Given a shell project
    And the file ".editorconfig" contains "[*.sh]\nindent_style = space"
    When the harness profiles the project
    Then the tooling does not name "shfmt"

  Scenario: An EditorConfig key only shfmt reads names the formatter of a shell project
    Given a shell project
    And the file ".editorconfig" contains "[*.sh]\nswitch_case_indent = true"
    When the harness profiles the project
    Then the tooling names "shfmt"
    And the command "format" is "shfmt -d ."

  Scenario: A vendored shunit2 is named and brings no command
    Given a shell project
    And the file "tests/shunit2" contains "# vendored"
    When the harness profiles the project
    Then the tooling names "shunit2"
    And the project names no command

  Scenario: A shell toolchain beside another stack is named, and does not become that stack's lint
    Given a Java project
    And the file "scripts/deploy.sh" contains "#!/bin/sh\necho deploying"
    And the file ".shellcheckrc" contains "disable=SC2086"
    When the harness profiles the project
    Then the languages are "java"
    And the tooling names "shellcheck"
    And no command is named "lint"

  Scenario: A command the requester declared wins over the one the harness derived
    Given a Python project
    And its pyproject.toml lists the dependency "pytest"
    And the requester declared the command "test" as "make check"
    When the harness profiles the project
    Then the command "test" is "make check"
