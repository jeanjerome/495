Feature: The paths a change is allowed to touch
  A scope check reads the files a change touched against the patterns the requester declared.
  A file matched by a forbidden pattern is a forbidden hit; a file no allowed pattern matches
  is a violation; a change that declares no allowed path may touch anything the forbidden
  patterns leave alone.

  Scenario: A file no allowed pattern matches is outside the scope
    Given a change touching "src/a.py, tests/test_a.py, README.md, .github/workflows/ci.yml, docs/x/y.md"
    And the allowed paths "src/**, tests/**"
    And the forbidden paths ".github/**"
    When the harness checks the scope
    Then the files outside the allowed paths are "README.md, docs/x/y.md"
    And the forbidden paths touched are ".github/workflows/ci.yml"
    And the change is out of scope
    And the summary says "forbidden"

  Scenario: A change that declares no allowed path may touch anything not forbidden
    Given a change touching "src/a.py"
    And no allowed path is declared
    And the forbidden paths ".495/**"
    When the harness checks the scope
    Then the change is within scope

  Scenario: A pattern naming one file matches that file
    Given a change touching "calc.py"
    And the allowed paths "calc.py, tests/**"
    And no path is forbidden
    When the harness checks the scope
    Then the change is within scope

  Scenario: A pattern with a double star matches at any depth
    Given a change touching "a/b/c.py"
    And the allowed paths "a/**/c.py"
    And no path is forbidden
    When the harness checks the scope
    Then the change is within scope

  Scenario: A directory pattern covers what it contains
    Given a change touching ".495/runs/x"
    And no allowed path is declared
    And the forbidden paths ".495/**"
    When the harness checks the scope
    Then the change is out of scope
    And the summary says "forbidden paths touched: .495/runs/x"
