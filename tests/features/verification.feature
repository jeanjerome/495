Feature: What a verification is worth before it runs, and what its runs show afterwards
  A verification is audited before the change is produced — whether its command can carry the
  requirement it is tied to at all — and read afterwards, from what it reported on the change
  and on the base version. Neither reading executes anything: the audit looks at the
  specification and at the commands the project already runs, and the pair of runs is handed
  in by whatever ran them.

  # ------------------------------------------------------------------ the audit

  Scenario: The audit names every requirement no verification can carry
    Given the requirement "R1" is verified by "V1", a test running "pytest -q"
    And the requirement "R2" is verified by "V2", a review
    And the requirement "R3" is verified by nothing
    And the requirement "R4" is verified by "V3", a command running "nonexistent-tool --check"
    And the project's verified commands are "pytest -q"
    When the harness audits the specification
    Then the verification "V1" is "sufficient"
    And the verification "V2" is "insufficient"
    And the verification "V3" is "insufficient"
    And the specification's gaps name "R2, R3, R4"

  Scenario: A command that exists on this machine but is not the project's is still sufficient
    Given the requirement "R1" is verified by "V1", a command running "echo hi"
    And the requirement "R2" is verified by "V2", a command running "no-such-tool-495 x"
    And the project's verified commands are "pytest -q"
    When the harness audits the specification
    Then the verification "V1" is "sufficient"
    And the rationale of "V1" says "is not one of the project's verified commands but exists on PATH"
    And the verification "V2" is "insufficient"
    And the specification's gaps name "R2"
    And the gap on "R2" reads "R2 has no sufficient verification (V2: insufficient (executable 'no-such-tool-495' not found on this machine))"

  Scenario Outline: Either spelling of an interpreter is replaced by the one the project uses
    Given the requirement "R1" is verified by "V1", a command running "<command>"
    And the project's verified commands are "/repo/.venv/bin/python -m pytest -q"
    When the harness audits the specification
    Then the command of "V1" is "<normalised>"
    And the rationale of "V1" says "replaced by the project's '/repo/.venv/bin/python'"
    And the verification "V1" is "sufficient"
    And the specification states no gap

    Examples:
      | command               | normalised                           |
      | python -c 'print(1)'  | /repo/.venv/bin/python -c 'print(1)' |
      | python3 -c 'print(1)' | /repo/.venv/bin/python -c 'print(1)' |

  Scenario: A command whose head is not an interpreter is left as it was written
    Given the requirement "R1" is verified by "V1", a command running "make lint"
    And the project's verified commands are "/repo/.venv/bin/python -m pytest -q, make lint"
    When the harness audits the specification
    Then the command of "V1" is "make lint"
    And "V1" states no rationale

  Scenario: A command that already passed on the base version cannot carry new behaviour
    Given the requirement "R1" is verified by "V1", a test running "mvn t"
    And the non-regression requirement "R2" is verified by "V1"
    And the requirement "R3" is verified by "V2", a test to create running "mvn t -Dtest=New"
    And "V2" states the scenario when "New runs" then "it asserts the behaviour"
    And the project's verified commands are "mvn t"
    And the command "mvn t" already passed on the base version
    When the harness audits the specification
    Then the specification's gaps name "R1"
    And the gap on "R1" says "already passed on the base version and creates nothing"

  Scenario: The same command carries new behaviour once it has not been run on the base
    Given the requirement "R1" is verified by "V1", a test running "mvn t"
    And the project's verified commands are "mvn t"
    And no command passed on the base version
    When the harness audits the specification
    Then the specification states no gap

  # ------------------------------------------------------------------ what failed, blind to when and where

  Scenario: Two runs that failed the same way share a signature, whenever and wherever they ran
    Given one run printed "FAILED at 10:04:11 in /Users/a/wt/x.py after 1.3 s (abc1234def5678)"
    And the other run printed "FAILED at 23:57:02 in /Users/b/other/x.py after 12.9 s (99ffee11223344)"
    When the two failures are signed
    Then the two signatures are the same

  Scenario: A different count is a different failure
    Given one run printed "Tests run: 7, Failures: 0"
    And the other run printed "Tests run: 7, Failures: 1"
    When the two failures are signed
    Then the two signatures differ

  Scenario: A failure for another reason is another signature
    Given one run printed "no tests matching pattern"
    And the other run printed "AssertionError: expected 3"
    When the two failures are signed
    Then the two signatures differ

  # ------------------------------------------------------------------ does the command see the change

  Scenario: A command that fails identically with and without the change sees nothing of it
    Given the change ran the command to exit 1 printing "no tests matching pattern NewTest"
    And without the change it exited 1 printing "no tests matching pattern NewTest"
    When the pair is read for what it tells of the change
    Then the command is not measuring the change

  Scenario: A failure for another reason on the change is a command that sees it
    Given the change ran the command to exit 1 printing "AssertionError: expected 3"
    And without the change it exited 1 printing "no tests matching pattern NewTest"
    When the pair is read for what it tells of the change
    Then the command is measuring the change

  Scenario: A different exit code is a command that sees the change
    Given the change ran the command to exit 2 printing "no tests matching pattern NewTest"
    And without the change it exited 1 printing "no tests matching pattern NewTest"
    When the pair is read for what it tells of the change
    Then the command is measuring the change

  Scenario: A timeout on the change leaves the instrument believed
    Given the command timed out on the change printing "no tests matching pattern NewTest"
    And without the change it exited 1 printing "no tests matching pattern NewTest"
    When the pair is read for what it tells of the change
    Then the command is measuring the change

  Scenario: A timeout without the change leaves the instrument believed
    Given the change ran the command to exit 1 printing "no tests matching pattern NewTest"
    And without the change it timed out printing "no tests matching pattern NewTest"
    When the pair is read for what it tells of the change
    Then the command is measuring the change

  # ------------------------------------------------------------------ what the pair says of the instrument

  Scenario: A command that reports something else without the change is believed
    Given a verification "V1" that passed on the change printing "2 passed"
    And without the change it exited 1 printing "E   assert 8 == 2"
    And the change's test files were carried over
    When the pair of runs is classified
    Then "V1" discriminates
    And the verification "V1" is "sufficient"

  Scenario: A command that fails identically on both versions is broken, not a defect of the change
    Given a verification "V1" that failed on the change printing "No tests matching pattern"
    And without the change it exited 1 printing "No tests matching pattern"
    And the change's test files were carried over
    When the pair of runs is classified
    Then "V1" does not discriminate
    And the verification "V1" is "broken"
    And the rationale of "V1" says "no edit inside the change can make it report success"

  Scenario: A command that passes on both versions proves nothing either
    Given a verification "V1" that passed on the change printing "ok"
    And without the change it exited 0 printing "ok"
    And the change's test files were carried over
    When the pair of runs is classified
    Then "V1" does not discriminate
    And the verification "V1" is "vacuous"
    And the rationale of "V1" says "it reports success either way"

  Scenario: Passing on both settles nothing when the test could not be carried over
    Given a verification "V1" that passed on the change printing "ok"
    And without the change it exited 0 printing "ok"
    And none of the change's test files could be carried over
    When the pair of runs is classified
    Then whether "V1" discriminates is not known
    And the verification "V1" is "sufficient"
    And the rationale of "V1" says "not enough to tell"

  # ------------------------------------------------------------------ which files are the instrument

  Scenario Outline: A path the usual layouts read as a test is the instrument
    Given the change touched "<path>"
    When the instrument files of the change are read
    Then "<path>" is one of them

    Examples:
      | path                                                          |
      | infrastructure/src/test/java/io/x/UserFileRepositoryTest.java |
      | tests/test_calc.py                                            |
      | pkg/foo_test.go                                               |
      | src/a.spec.ts                                                 |
      | src/__tests__/a.js                                            |
      | features/login.feature                                        |

  Scenario Outline: A path no naming convention reads as a test is what the change delivers
    Given the change touched "<path>"
    When the instrument files of the change are read
    Then "<path>" is not one of them

    Examples:
      | path                                                          |
      | infrastructure/src/main/java/io/x/UserFileRepository.java     |
      | src/latest.py                                                 |
      | docs/testing.md                                               |
